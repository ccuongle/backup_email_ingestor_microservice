
import unittest
import pytest
from testcontainers.rabbitmq import RabbitMqContainer
from utils.rabbitmq import RabbitMQConnection
import pika

class TestRabbitMQIntegration(unittest.TestCase):

    @pytest.mark.integration
    def test_connection_and_channel(self):
        """
        Test Case ID: 1.1-INT-001
        Test successful connection and channel creation to a real RabbitMQ instance.
        """
        with RabbitMqContainer("rabbitmq:3.12-management") as rabbitmq_container:
            host = rabbitmq_container.get_container_host_ip()
            port = rabbitmq_container.get_container_port(5672)
            credentials = pika.PlainCredentials('guest', 'guest')
            
            config = {
                'host': host,
                'port': port,
                'credentials': credentials
            }

            with RabbitMQConnection(**config) as manager:
                self.assertIsNotNone(manager.connection)
                self.assertTrue(manager.connection.is_open)
                self.assertIsNotNone(manager.channel)
                self.assertTrue(manager.channel.is_open)

    @pytest.mark.integration
    def test_connection_failure(self):
        """
        Test Case ID: 1.1-INT-002
        Test graceful failure when attempting to connect with invalid credentials.
        """
        with RabbitMqContainer("rabbitmq:3.12-management") as rabbitmq_container:
            host = rabbitmq_container.get_container_host_ip()
            port = rabbitmq_container.get_container_port(5672)
            # Invalid credentials
            credentials = pika.PlainCredentials('invalid', 'user')
            
            config = {
                'host': host,
                'port': port,
                'credentials': credentials
            }

            with self.assertRaises(pika.exceptions.ProbableAuthenticationError):
                RabbitMQConnection(**config).connect()

    @pytest.mark.integration
    def test_publish_receive_cycle(self):
        """
        Test Case ID: 1.1-INT-003
        Test a full publish-and-receive cycle through a real RabbitMQ instance.
        """
        with RabbitMqContainer("rabbitmq:3.12-management") as rabbitmq_container:
            host = rabbitmq_container.get_container_host_ip()
            port = rabbitmq_container.get_container_port(5672)
            credentials = pika.PlainCredentials('guest', 'guest')
            
            config = {
                'host': host,
                'port': port,
                'credentials': credentials
            }

            queue_name = 'test_queue'
            test_message = 'Hello, RabbitMQ!'
            
            with RabbitMQConnection(**config) as manager:
                # Declare a queue for testing
                manager.channel.queue_declare(queue=queue_name)
                
                # Publish a message
                manager.publish_message(exchange='', routing_key=queue_name, body=test_message)

                # Consume the message
                method_frame, header_frame, body = manager.channel.basic_get(queue=queue_name, auto_ack=True)
                
                self.assertIsNotNone(method_frame)
                self.assertEqual(body.decode('utf-8'), test_message)

if __name__ == '__main__':
    unittest.main()
