# Danfoss Ally Scheduler

A Python tool for scheduling Danfoss Ally thermostats via MQTT (Zigbee2MQTT). This tool allows you to:
- Configure weekly schedules for multiple thermostats
- Save and load configurations
- Apply schedules to selected days and devices

## Installation
```bash
poetry install
poetry shell
```

## Configuration
Create a `config.yaml` file in the `~/.danfoss_ally/` directory:
```yaml
mqtt:
  host: 'mqtt.example.com'
  port: 1883
  username: 'your_mqtt_username'
  password: 'your_mqtt_password'
  topic_discovery: 'zigbee2mqtt/bridge/devices'
  topic_set: 'zigbee2mqtt/{}/1/set'
```

## Usage
### Interactive configuration
```bash
python -m danfoss_ally_scheduler
```

### Load and apply configuration
```bash
python -m danfoss_ally_scheduler --load
```

### Load specific configuration
```bash
python -m danfoss_ally_scheduler --load path/to/schedule_config.yaml
```

## TODO
- [ ] Add support for clearing schedules
- [ ] Web interface
- [ ] Docker image
- [ ] Integration tests

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
