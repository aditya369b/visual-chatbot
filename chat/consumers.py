from channels import Group
from chat.utils import log_to_terminal
import json
import ujson
import base64

def ws_connect(message):
    print("User connnected via Socket")


def ws_message(message):
    print("Message recieved from client side and the content is ", message.content['text'])
    # prefix, label = message['path'].strip('/').split('/')
    socketid = message.content['text']
    
    Group(socketid).add(message.reply_channel)
    log_to_terminal(socketid, {"info": "User added to the Channel Group"})


def ws_check(message):
	Group('users').add(message.reply_channel)	
	Group('users').send({
		'text' : json.dumps(message.content)
		});
			# Send binary data (image)
	
	#Group('users').send({
	#	'image': message
	#	});

	print("Message received from ws connect")

def ws_check2(message):
	print("ws got connected: ", message.content)
