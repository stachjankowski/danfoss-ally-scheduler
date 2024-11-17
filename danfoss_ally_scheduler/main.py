from argparse import ArgumentParser
from dataclasses import dataclass
from typing import List, Dict, Optional 

from danfoss_ally_scheduler.mqtt_config import MQTTConfig
from danfoss_ally_scheduler.thermostat_manager import ThermostatManager


def main():
    parser = ArgumentParser(description='Danfoss Ally Thermostat Scheduler')
    parser.add_argument('--load', action='store_true', 
                       help='Load and apply schedule from saved configuration')
    parser.add_argument('--config', type=str,
                       help='Path to configuration file (optional)')
    args = parser.parse_args()

    try:
        config = MQTTConfig.from_yaml()
        manager = ThermostatManager(config)
        
        if args.load:
            manager.load_and_apply_schedule(args.config)
        else:
            manager.configure_schedule()
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
