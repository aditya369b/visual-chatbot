from __future__ import absolute_import

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'visdial.settings')

import django
django.setup()

from django.conf import settings
from chat.utils import log_to_terminal
from chat.models import Job, Dialog

import chat.constants as constants

import pika
import yaml
import json
import traceback

from models import CaptioningTorchDummyModel

django.db.close_old_connections()

#####
# TODO: Move args to config file
import argparse
import os

import torch
import yaml

from viscap.captioning import DetectCaption, build_detection_model, build_caption_model
from viscap.visdialch.data import Vocabulary
from viscap.visdialch.data.demo_manager import DemoSessionManager
from viscap.visdialch.model import EncoderDecoderModel

parser = argparse.ArgumentParser(
    "Run Visual-Dialog Demo"
)

parser.add_argument(
    "--config-yml",
    default="configs/lf_gen_faster_rcnn_x101_demo.yml",
    help="Path to a config file listing reader, visual dialog and captioning "
         "model parameters.",
)

parser.add_argument(
    "--load-pthpath",
    default="checkpoints/lf_gen_faster_rcnn_x101_train.pth",
    help="Path to .pth file of pretrained checkpoint.",
)

parser.add_argument(
    "--gpu-ids",
    nargs="+",
    type=int,
    default=0,
    help="List of ids of GPUs to use.",
)

# For reproducibility.
# Refer https://pytorch.org/docs/stable/notes/randomness.html
torch.manual_seed(0)
torch.cuda.manual_seed_all(0)
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = True

# =============================================================================
#   INPUT ARGUMENTS AND CONFIG
# =============================================================================

args = parser.parse_args()
# get abs path
if not os.path.isabs(args.config_yml):
    args.config_yml = os.path.abspath(args.config_yml)

# keys: {"dataset", "model", "solver"}
config = yaml.load(open(args.config_yml), Loader=yaml.FullLoader)

if isinstance(args.gpu_ids, int):
    args.gpu_ids = [args.gpu_ids]
device = (
    torch.device("cuda", args.gpu_ids[0])
    if args.gpu_ids[0] >= 0
    else torch.device("cpu")
)

# Print config and args.
print(yaml.dump(config, default_flow_style=False))
for arg in vars(args):
    print("{:<20}: {}".format(arg, getattr(args, arg)))

# =============================================================================
#   BUILD VOCABULARY | LOAD MODELS: ENC-DEC, CAPTIONING
# =============================================================================
dataset_config = config["dataset"]
model_config = config["model"]
captioning_config = config["captioning"]

vocabulary = Vocabulary(
    dataset_config["word_counts_json"],
    min_count=dataset_config["vocab_min_count"]
)

# Build Encoder-Decoder model and load its checkpoint
enc_dec_model = EncoderDecoderModel(model_config, vocabulary).to(device)
enc_dec_model.load_checkpoint(args.load_pthpath)

# Build the detection and captioning model and load their checkpoints
# Path to the checkpoints are picked from captioning_config
detection_model = build_detection_model(captioning_config, device)
caption_model, caption_processor, text_processor = build_caption_model(
    captioning_config,
    device
)

# Wrap the detection and caption models together
detect_caption_model = DetectCaption(
    detection_model,
    caption_model,
    caption_processor,
    text_processor,
    device
)

# Pass the Captioning and Encoder-Decoder models and initialize DemoObject
demo_manager = DemoSessionManager(
    detect_caption_model,
    enc_dec_model,
    vocabulary,
    config,
    device
)

# =============================================================================
#   EVALUATION LOOP
# =============================================================================

enc_dec_model.eval()
# # Extract features and build caption for the image
# demo_manager.set_image(args.imagepath)
# print(f"Caption: {demo_manager.get_caption()}")
# while True:
#     user_question = input("Type Question: ").lower()
#     answer = demo_manager.respond(user_question)
#     print(f"Answer: {answer}")
#     demo_manager.update(question=user_question, answer=answer)
#
#     while True:
#         user_input = input("Change Image? [(y)es/(n)o]: ").lower()
#         if user_input == 'y' or user_input == 'yes':
#             print("-"*50)
#             user_image = input("Enter New Image Path: ")
#             demo_manager.set_image(user_image)
#             print(f"Caption: {demo_manager.get_caption()}")
#
#         elif user_input == 'n' or user_input == 'no':
#             break

#####

connection = pika.BlockingConnection(pika.ConnectionParameters(
    host='localhost'))

channel = connection.channel()

channel.queue_declare(queue='visdial_caption_task_queue', durable=True)
print(' [*] Waiting for messages. To exit press CTRL+C')


def callback(ch, method, properties, body):
    try:
        body = yaml.safe_load(body)

        if body['type'] == "visdial":
            # go for the visdial-run
            answer = demo_manager.respond(body['input_question'])
            log_to_terminal(body['socketid'], {"answer": answer})
            ch.basic_ack(delivery_tag=method.delivery_tag)
            try:
                job = Job.objects.get(id=int(body['job_id']))
                Dialog.objects.create(job=job, question=body['input_question'], answer=answer)
            except:
                print(str(traceback.print_exc()))

        else:
            # go for the caption-run
            demo_manager.set_image(body['image_path'])
            caption = demo_manager.get_caption()
            log_to_terminal(body['socketid'], {"caption": caption})
            ch.basic_ack(delivery_tag=method.delivery_tag)
            try:
                Job.objects.filter(id=int(body['job_id'])).update(
                    caption=caption
                )
            except Exception as e:
                print(str(traceback.print_exc()))
        django.db.close_old_connections()

    except Exception:
        print(str(traceback.print_exc()))


channel.basic_consume(callback, queue='visdial_caption_task_queue')
channel.start_consuming()
