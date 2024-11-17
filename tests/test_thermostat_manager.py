import pytest
from unittest.mock import Mock, patch
from danfoss_ally_scheduler.thermostat_manager import ThermostatManager, MINIMUM_TEMPERATURE, MAXIMUM_TEMPERATURE, ALLOWED_TEMPERATURE_STEP
from danfoss_ally_scheduler.mqtt_config import MQTTConfig


@pytest.fixture
def mqtt_config():
    return MQTTConfig(
        broker="test.broker",
        port=1883,
        user="test_user",
        password="test_pass",
        topic_discovery="zigbee2mqtt/bridge/devices",
        topic_set="zigbee2mqtt/{}/set",
        use_tls=False
    )


@pytest.fixture
def thermostat_manager(mqtt_config):
    with patch('paho.mqtt.client.Client') as mock_client:
        manager = ThermostatManager(mqtt_config, dry_run=True)
        manager.client = mock_client
        return manager


def test_parse_schedule_entry(thermostat_manager):
    entry = thermostat_manager._parse_schedule_entry("08:30", "21.5")
    assert entry == {
        "time": "08:30",
        "transitionTime": 510,
        "heatSetpoint": 2150,
        "temperature": 21.5
    }


def test_parse_schedule_entry_invalid_time(thermostat_manager):
    with pytest.raises(ValueError, match="Time must be in format HH:MM"):
        thermostat_manager._parse_schedule_entry("25:00", "21.5")


def test_parse_schedule_entry_invalid_temperature(thermostat_manager):
    with pytest.raises(ValueError, match="Invalid input format"):
        thermostat_manager._parse_schedule_entry("08:30", "invalid")


def test_prepare_schedule_payload(thermostat_manager):
    schedule = [
        {"time": "08:30", "transitionTime": 510, "heatSetpoint": 2150, "temperature": 21.5}
    ]
    selected_days = ["Monday", "Wednesday"]
    
    payload = thermostat_manager._prepare_schedule_payload(schedule, selected_days)
    
    assert payload == {
        "command": {
            "cluster": 513,
            "command": 1,
            "payload": {
                "dayofweek": 5,  # binary: 101 (Monday + Wednesday)
                "mode": 1,
                "numoftrans": 1,
                "transitions": schedule
            }
        }
    }


def test_send_schedule_to_thermostats(thermostat_manager):
    selected_thermostats = ["thermostat1", "thermostat2"]
    payload = {"test": "payload"}
    
    # Configure mock
    mock_publish = thermostat_manager.client.publish
    mock_publish.return_value = Mock(is_published=lambda: True)
    
    thermostat_manager._send_schedule_to_thermostats(selected_thermostats, payload)
    
    # Check if publish was called for each thermostat
    assert mock_publish.call_count == 2
    
    # Optionally, we can also check the exact calls
    expected_calls = [
        ((f"zigbee2mqtt/{thermostat}/set", '{\n  "test": "payload"\n}'), {})
        for thermostat in selected_thermostats
    ]
    mock_publish.assert_has_calls(expected_calls)


def test_select_days_empty_input(thermostat_manager):
    with patch('builtins.input', return_value=""):
        result = thermostat_manager._select_days(set(["Monday", "Tuesday"]))
        assert result == []


def test_select_days_invalid_input(thermostat_manager):
    with patch('builtins.input', return_value="invalid"):
        result = thermostat_manager._select_days(set(["Monday", "Tuesday"]))
        assert result == []


def test_select_thermostats_empty_list(thermostat_manager):
    thermostat_manager.thermostats = []
    result = thermostat_manager._select_thermostats()
    assert result == []


def test_select_thermostats_invalid_input(thermostat_manager):
    thermostat_manager.thermostats = ["thermostat1", "thermostat2"]
    with patch('builtins.input', return_value="invalid"):
        result = thermostat_manager._select_thermostats()
        assert result == []


def test_save_schedule_to_yaml(thermostat_manager, tmp_path):
    schedule = [
        {"time": "08:30", "transitionTime": 510, "heatSetpoint": 2150, "temperature": 21.5}
    ]
    selected_days = ["Monday", "Wednesday"]
    selected_thermostats = ["thermostat1"]
    
    config_dir = tmp_path / '.danfoss_ally'
    config_file = config_dir / 'schedule_config.yaml'
    
    with patch('pathlib.Path.home', return_value=tmp_path):
        thermostat_manager.save_schedule_to_yaml(schedule, selected_days, selected_thermostats)
        
        assert config_dir.exists()
        assert config_file.exists()
        
        with open(config_file) as f:
            content = f.read()
            assert "schedule:" in content
            assert "days:" in content
            assert "thermostats:" in content


def test_load_and_apply_schedule(thermostat_manager, tmp_path):
    config_content = """
schedule:
- time: '08:30'
  temperature: 21.5
days:
- Monday
- Wednesday
thermostats:
- thermostat1
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    
    # Configure mock
    mock_publish = thermostat_manager.client.publish
    mock_publish.return_value = Mock(is_published=lambda: True)
    
    thermostat_manager.load_and_apply_schedule(str(config_file))
    
    mock_publish.assert_called_once()
    call_args = mock_publish.call_args[0]
    assert "thermostat1" in call_args[0]
    assert '"dayofweek": 5' in call_args[1]  # 5 = binary 101 (Monday + Wednesday)


def test_load_and_apply_schedule_file_not_found(thermostat_manager, tmp_path):
    nonexistent_file = tmp_path / "nonexistent.yaml"
    with patch('builtins.print') as mock_print:
        thermostat_manager.load_and_apply_schedule(str(nonexistent_file))
        mock_print.assert_called_with(f"Configuration file not found: {nonexistent_file}")
