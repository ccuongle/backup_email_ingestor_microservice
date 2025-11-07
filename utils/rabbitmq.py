import pika
import logging
from . import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RabbitMQConnection:
    """
    Manages RabbitMQ connection, channel creation, and basic publishing/consuming logic.
    
    NOTE: This class does NOT create queues or exchanges.
    Queue topology is managed by the external Queue Orchestrator service.
    """
    def __init__(self):
        self.connection = None
        self.channel = None
        self.host = config.RABBITMQ_HOST
        self.port = config.RABBITMQ_PORT
        self.username = config.RABBITMQ_USERNAME
        self.password = config.RABBITMQ_PASSWORD
        self.virtual_host = config.RABBITMQ_VIRTUAL_HOST

    def connect(self):
        """Establishes a connection to RabbitMQ."""
        try:
            credentials = pika.PlainCredentials(self.username, self.password)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    virtual_host=self.virtual_host,
                    credentials=credentials
                )
            )
            self.channel = self.connection.channel()
            logger.info("Successfully connected to RabbitMQ.")
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    def close(self):
        """Closes the RabbitMQ connection."""
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("RabbitMQ connection closed.")

    def ensure_queue_exists(self, queue_name: str):
        """
        Verify queue exists using passive declare.
        Does NOT create the queue - Queue Orchestrator handles that.
        
        Args:
            queue_name: Name of the queue to check
            
        Raises:
            ChannelClosedByBroker: If queue doesn't exist
        """
        if not self.channel:
            self.connect()
        try:
            self.channel.queue_declare(queue=queue_name, passive=True)
            logger.info(f"Queue '{queue_name}' exists and is accessible.")
        except pika.exceptions.ChannelClosedByBroker:
            logger.error(f"Queue '{queue_name}' does not exist. Must be created by Queue Orchestrator.")
            raise

    def publish(self, exchange: str, routing_key: str, body: str):
        """
        Publishes a message to an exchange.
        
        Args:
            exchange: Exchange name (managed by Queue Orchestrator)
            routing_key: Routing key for message routing
            body: Message payload (should be JSON string)
        """
        if not self.channel:
            self.connect()
        try:
            self.channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                )
            )
            logger.info(f"Message published to exchange '{exchange}' with routing key '{routing_key}'.")
        except pika.exceptions.AMQPChannelError as e:
            logger.error(f"Failed to publish message to exchange '{exchange}' with routing key '{routing_key}': {e}")
            raise

    def consume(self, queue_name: str, callback):
        """
        Starts consuming messages from a queue.
        Queue must be created by Queue Orchestrator before calling this method.
        
        Args:
            queue_name: Name of the queue to consume from
            callback: Function to handle incoming messages
        """
        if not self.channel:
            self.connect()
        
        # Verify queue exists (passive check only)
        self.ensure_queue_exists(queue_name)
        
        def safe_callback(ch, method, properties, body):
            try:
                callback(ch, method, properties, body)
            except Exception as e:
                logger.error(f"Error processing message: {e}. Nacking message {method.delivery_tag}")
                self.nack_message(method.delivery_tag)

        self.channel.basic_consume(
            queue=queue_name, 
            on_message_callback=safe_callback, 
            auto_ack=False
        )
        logger.info(f"Started consuming from queue '{queue_name}'. Waiting for messages...")
        self.channel.start_consuming()

    def ack_message(self, delivery_tag):
        """Acknowledges a message."""
        if self.channel:
            self.channel.basic_ack(delivery_tag)

    def nack_message(self, delivery_tag, requeue=True):
        """Negative acknowledges a message."""
        if self.channel:
            self.channel.basic_nack(delivery_tag, requeue=requeue)