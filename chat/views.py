import os
import random
import urllib
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render

import chat.constants as constants
from .models import Job
from .sender import viscap
from rest_framework.decorators import api_view
import cProfile, pstats, io, time
# from pstats import SortKey

# pr = cProfile.Profile()

@api_view(['GET','POST'])
def home(request, template_name="chat/index.html"):
    socketid = uuid.uuid4()
    intro_message = random.choice(constants.BOT_INTORDUCTION_MESSAGE)

    if request.method == "POST":
        try:
            socketid = request.POST.get("socketid")
            question = request.POST.get("question")
            img_path = request.POST.get("img_path")
            job_id = request.POST.get("job_id")
            image_key = request.POST.get("image_key")
            history = request.POST.get("history", "")
            img_path = urllib.parse.unquote(img_path)
            abs_image_path = str(img_path)
            # pr.enable()
            print('image key: ',image_key, type(image_key))
            viscap(str(abs_image_path), socketid, job_id, None, str(question), str(history), str(image_key))
            # pr.disable()
            # s = io.StringIO()
            # # sortby = SortKey.CUMULATIVE
            # sortby = "cumulative"
            # ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            # ps.print_stats()
            # print(s.getvalue())

            return JsonResponse({"success": True})
        except Exception:
            return JsonResponse({"success": False})

    elif request.method == "GET":
        return render(request, template_name, {
                                               "socketid": socketid,
                                               "bot_intro_message": intro_message})


# Create a Job for captioning
@api_view(['POST'])
def upload_image(request):

    if request.method == "POST":
        image = request.FILES.get('file')
        socketid = request.POST.get('socketid')
        pythia_caption = request.POST.get('pythia_caption')
        output_dir = os.path.join(settings.MEDIA_ROOT, 'svqa', socketid)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        img_path = os.path.join(output_dir, str(image))
        handle_uploaded_file(image, img_path)
        img_url = img_path.replace(settings.BASE_DIR, "")
        job = Job.objects.create(job_id=socketid, image=img_url)
        viscap(img_path, socketid, job.id, pythia_caption)

        return JsonResponse({"file_path": img_path, "img_url": img_url, "job_id": job.id})
    else:
        raise TypeError("Only POST requests allowed, check request method!")


def handle_uploaded_file(f, path):
    with open(path, 'wb+') as destination:
        for chunk in f.chunks():
            destination.write(chunk)
