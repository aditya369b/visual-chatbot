import json
import pika


def viscap(image_path, socketid, job_id, pythia_caption=None, input_question=None, history=None, image_key=None):
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host='localhost'))
    channel = connection.channel()
    routing_key = "visdial_caption_task_queue"

    if input_question is None and history is None:
        channel.queue_declare(queue=routing_key, durable=True)
        message = {
            'image_path': image_path,
            'socketid': socketid,
            'job_id': job_id,
            'pythia_caption': pythia_caption,
            'type': "caption"
        }

    else:
        channel.queue_declare(queue=routing_key, durable=True)
        message = {
            'image_path': image_path,
            'input_question': input_question,
            'history': history,
            'socketid': socketid,
            'image_key': image_key,
            'job_id': job_id,
            'type': "visdial"
        }

    channel.basic_publish(exchange='',
                          routing_key=routing_key,
                          body=json.dumps(message),
                          properties=pika.BasicProperties(
                              delivery_mode=2,  # make message persistent
                          ))
    connection.close()
