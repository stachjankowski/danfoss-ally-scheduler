from dataclasses import dataclass
import yaml
from pathlib import Path
from typing import Optional


@dataclass
class MQTTConfig:
    """MQTT connection configuration.
    
    Attributes:
        broker: MQTT broker address
        port: MQTT port
        user: Username
        password: Password
        topic_discovery: Topic for device discovery
        topic_set: Topic format for setting parameters
        use_tls: Whether to use TLS for the MQTT connection
        ca_certs: Path to CA certificates for TLS
        certfile: Path to client certificate for TLS
        keyfile: Path to client key for TLS
    """
    broker: str
    port: int
    user: str
    password: str
    topic_discovery: str
    topic_set: str
    use_tls: bool = False
    ca_certs: Optional[str] = None
    certfile: Optional[str] = None
    keyfile: Optional[str] = None

    @classmethod
    def from_yaml(cls, config_path: Optional[Path] = None) -> 'MQTTConfig':
        """Reads configuration from a YAML file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            MQTTConfig: Configuration object
        """
        if config_path is None:
            config_path = Path.home() / '.danfoss_ally' / 'config.yaml'
            
        with open(config_path) as f:
            config = yaml.safe_load(f)['mqtt']
            
        return cls(**config) 


    def validate(self) -> None:
        """Validates the MQTT configuration."""
        if not all([self.broker, self.port, self.user, self.password]):
            raise ValueError("Required MQTT configuration fields are missing")
        
        if self.use_tls and not self.ca_certs:
            raise ValueError("CA certificates path is required when TLS is enabled")
