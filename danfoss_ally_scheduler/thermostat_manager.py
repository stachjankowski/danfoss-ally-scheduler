import json
from pathlib import Path
import time
from typing import List, Optional, Dict
import yaml

from paho.mqtt import client as mqtt_client

from danfoss_ally_scheduler.mqtt_config import MQTTConfig


MINIMUM_TEMPERATURE = 5.0
MAXIMUM_TEMPERATURE = 35.0
ALLOWED_TEMPERATURE_STEP = 0.5


class ThermostatManager:
    """Manages thermostats via MQTT."""
    
    MODEL = '014G2461'
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self, mqtt_config: MQTTConfig, dry_run: bool = False):
        """Initialize ThermostatManager.
        
        Args:
            mqtt_config: MQTT Configuration
            dry_run: If True, don't send actual commands to devices
        """
        self.mqtt_config = mqtt_config
        self.dry_run = dry_run
        self.client: Optional[mqtt_client.Client] = None
        self.thermostats: List[str] = []
        if not dry_run:
            self._connect_mqtt()
            self.fetch_thermostats()

    def _connect_mqtt(self) -> None:
        """Connects to MQTT broker with TLS support."""
        try:
            self.mqtt_config.validate()
            
            self.client = mqtt_client.Client()
            self.client.username_pw_set(self.mqtt_config.user, self.mqtt_config.password)
            
            if self.mqtt_config.use_tls:
                self.client.tls_set(
                    ca_certs=self.mqtt_config.ca_certs,
                    certfile=self.mqtt_config.certfile,
                    keyfile=self.mqtt_config.keyfile
                )
            
            # Add callbacks for connection
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    print("Connected to MQTT broker")
                else:
                    raise ConnectionError(f"Failed to connect to MQTT broker: {rc}")
                
            def on_disconnect(client, userdata, rc):
                print(f"Disconnected from MQTT broker: {rc}")
            
            self.client.on_connect = on_connect
            self.client.on_disconnect = on_disconnect
            
            # Try to connect with timeout
            self.client.connect(self.mqtt_config.broker, self.mqtt_config.port)
            self.client.loop_start()
            time.sleep(2)  # Wait for connection
            
            if not self.client.is_connected():
                raise ConnectionError("Failed to connect to MQTT broker")
            
        except Exception as e:
            self.client = None
            raise ConnectionError(f"MQTT connection failed: {str(e)}")
    
    def fetch_thermostats(self) -> None:
        """Fetch thermostats from MQTT."""
        def on_message(_, __, msg):
            try:
                devices = json.loads(msg.payload)
                for device in devices:
                    if device.get('definition', {}).get('model') == self.MODEL:
                        device_id = device.get('friendly_name')
                        if device_id and device_id not in self.thermostats:
                            self.thermostats.append(device_id)
                print(f"Found {len(self.thermostats)} thermostats")
            except json.JSONDecodeError:
                print("JSON decoding error from MQTT")
            except Exception as e:
                print(f"An error occurred while fetching thermostats: {str(e)}")

        self.client.subscribe(self.mqtt_config.topic_discovery)
        self.client.on_message = on_message
        self.client.loop_start()
        time.sleep(2)
        self.client.loop_stop()
        self.client.unsubscribe(self.mqtt_config.topic_discovery)
        self.client.on_message = None

    def configure_schedule(self) -> None:
        """Configure schedule for selected thermostats and days."""
        remaining_days = set(self.DAYS)
        
        selected_thermostats = self._select_thermostats()
        if not selected_thermostats:
            print("Configuration cancelled.")
            return
        
        while remaining_days:
            print(f"\nRemaining days to configure: {', '.join(remaining_days)}")
            selected_days = self._select_days(remaining_days)
            
            if not selected_days:
                print("Configuration cancelled.")
                return
            
            schedule = self._get_schedule_from_user()
            if not schedule:
                print("No data entered.")
                continue

            payload = self._prepare_schedule_payload(schedule, selected_days)
            self._send_schedule_to_thermostats(selected_thermostats, payload)
            
            remaining_days -= set(selected_days)
            
            print("\nReport:")
            print(f"Configured days: {', '.join(selected_days)}")
            print(f"For thermostats: {', '.join(selected_thermostats)}")
            print("Schedule:", json.dumps(schedule, indent=2))

        self.save_schedule_to_yaml(schedule, selected_days, selected_thermostats)

    def _get_schedule_from_user(self) -> List[Dict]:
        """Gets schedule from user."""
        schedule = []
        while True:
            print("\nEnter time and temperature (or skip to finish):")
            time_input = input("Time (HH:MM): ").strip()
            if time_input == "":
                break
            try:
                temp_input = input("Temperature (°C): ").strip()
                schedule.append(self._parse_schedule_entry(time_input, temp_input))
            except ValueError:
                print("Invalid format. Try again.")
        return schedule

    def _parse_schedule_entry(self, time_input: str, temperature_input: str) -> Dict:
        """Parses a single schedule entry.
        
        Args:
            time_input: Time in HH:MM format
            temperature_input: Temperature value as string
        
        Returns:
            Dict containing parsed schedule entry
        
        Raises:
            ValueError: When input format is invalid or values are out of range
        """
        try:
            hour, minute = map(int, time_input.split(":"))
            
            # Time validation
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Time must be in format HH:MM (00:00-23:59)")
            
            # Temperature validation
            temperature = float(temperature_input)

            if not (MINIMUM_TEMPERATURE <= temperature <= MAXIMUM_TEMPERATURE):
                raise ValueError(f"Temperature must be between {MINIMUM_TEMPERATURE}°C and {MAXIMUM_TEMPERATURE}°C")
            
            if temperature % ALLOWED_TEMPERATURE_STEP != 0:
                raise ValueError(f"Temperature must be a multiple of {ALLOWED_TEMPERATURE_STEP}°C")
            
            return {
                "time": f"{hour:02d}:{minute:02d}",
                "transitionTime": hour * 60 + minute,
                "heatSetpoint": int(temperature * 100),
                "temperature": temperature
            }
        except ValueError as e:
            if "Time must be in format" not in str(e):
                raise ValueError("Invalid input format")
            raise

    def _select_days(self, remaining_days: set) -> List[str]:
        """Allows user to select days of the week.
        
        Args:
            remaining_days: Set of days that still need to be configured
        """
        print("\nSelect days (enter numbers separated by commas):")
        for i, day in enumerate(self.DAYS, 1):
            if day in remaining_days:
                print(f"{i}. {day}")
        
        try:
            selection = input("Selected days (e.g. 1,2,3): ").strip()
            if not selection:
                return []
            
            selected_indices = [int(x.strip()) - 1 for x in selection.split(",")]
            selected_days = []
            for i in selected_indices:
                if 0 <= i < len(self.DAYS) and self.DAYS[i] in remaining_days:
                    selected_days.append(self.DAYS[i])
                else:
                    print(f"Invalid day index: {i}")
            return selected_days
        except (ValueError, IndexError):
            print("Invalid format. Try again.")
            return []

    def _select_thermostats(self) -> List[str]:
        """Allows user to select thermostats."""
        if not self.thermostats:
            print("No thermostats found.")
            return []
            
        print("\nSelect thermostats (enter numbers separated by commas):")
        for i, thermostat in enumerate(self.thermostats, 1):
            print(f"{i}. {thermostat}")
        
        try:
            selection = input("Selected thermostats (e.g. 1,2,3): ").strip()
            if not selection:
                return []
            
            selected_indices = [int(x.strip()) - 1 for x in selection.split(",")]
            return [self.thermostats[i] for i in selected_indices if 0 <= i < len(self.thermostats)]
        except (ValueError, IndexError):
            print("Invalid format. Try again.")
            return []

    def _prepare_schedule_payload(self, schedule: List[Dict], selected_days: List[str]) -> Dict:
        """Prepares payload for schedule MQTT.
        
        Args:
            schedule: List of schedule entries
            selected_days: List of selected days
        
        Returns:
            Dict: Prepared payload for MQTT 
        """
        return {
            "command": {
                "cluster": 513,
                "command": 1,
                "payload": {
                    "dayofweek": sum(1 << self.DAYS.index(day) for day in selected_days),
                    "mode": 1,
                    "numoftrans": len(schedule),
                    "transitions": schedule
                }
            }
        }

    def _send_schedule_to_thermostats(self, selected_thermostats: List[str], payload: Dict) -> None:
        """Sends schedule to selected thermostats."""
        for thermostat in selected_thermostats:
            topic = self.mqtt_config.topic_set.format(thermostat)
            payload_json = json.dumps(payload, indent=2)
            
            print(f"{'[DRY-RUN] ' if self.dry_run else ''}Sending schedule to {thermostat}")
            print(f"Topic: {topic}")
            print(f"Payload: {payload_json}")
            
            # Zawsze wywołujemy publish, nawet w trybie dry-run
            message_info = self.client.publish(topic, payload_json)
            
            if not self.dry_run:
                if not message_info.is_published():
                    print(f"Failed to send schedule to {thermostat}")

    def save_schedule_to_yaml(self, schedule: List[Dict], selected_days: List[str], selected_thermostats: List[str]) -> None:
        """Saves schedule to YAML file.
        
        Args:
            schedule: List of schedule entries
            selected_days: List of selected days
            selected_thermostats: List of selected thermostats
        """
        # Simplify schedule data for YAML
        simplified_schedule = [{
            'time': entry['time'],
            'temperature': entry['temperature']
        } for entry in schedule]
        
        config_data = {
            'schedule': simplified_schedule,
            'days': selected_days,
            'thermostats': selected_thermostats
        }
        
        config_dir = Path.home() / '.danfoss_ally'
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / 'schedule_config.yaml'
        
        with open(config_file, 'a') as f:
            f.write('\n---\n')  # Separator for multiple YAML documents
            yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
            
        print(f"\nConfiguration saved to: {config_file}")

    def load_and_apply_schedule(self, config_file: Optional[str] = None) -> None:
        """Load schedule from YAML file and apply it to thermostats."""
        if config_file is None:
            config_file = Path.home() / '.danfoss_ally' / 'schedule_config.yaml'
        
        try:
            with open(config_file, 'r') as f:
                configs = list(yaml.safe_load_all(f))
            
            for config in configs:
                # Convert human-readable format to thermostat format
                schedule = []
                for entry in config['schedule']:
                    hour, minute = map(int, entry['time'].split(':'))
                    schedule.append({
                        'transitionTime': hour * 60 + minute,
                        'heatSetpoint': int(entry['temperature'] * 100)
                    })
                
                payload = self._prepare_schedule_payload(schedule, config['days'])
                self._send_schedule_to_thermostats(config['thermostats'], payload)
                time.sleep(1)
                
                print("\nApplied configuration:")
                print(f"Days: {', '.join(config['days'])}")
                print(f"Thermostats: {', '.join(config['thermostats'])}")
                print("Schedule:")
                for entry in config['schedule']:
                    print(f"  {entry['time']}: {entry['temperature']}°C")
                
        except FileNotFoundError:
            print(f"Configuration file not found: {config_file}")
        except Exception as e:
            print(f"Error loading configuration: {e}")
