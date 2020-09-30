import os
import torch
import codecs, json 
import numpy as np
import pickle

from typing import Any, Dict, Optional
from nltk.tokenize.treebank import TreebankWordDetokenizer
from nltk.tokenize import word_tokenize
from torch.nn.functional import normalize
from urllib.parse import urlparse

from viscap.captioning import DetectCaption
from viscap.visdialch.data import Vocabulary
from viscap.visdialch.model import EncoderDecoderModel
from viscap.visdialch.utils.history_builder import pad_sequences, get_history

class DemoSessionManager:
    """
    Maintains the complete demo session: captioning, dialogs, history updates.

    Inside a lifecycle of the demo session, we proceed in the following order:
    1. Intialize ``DemoSessionManager``.
    2. Call ``set_image`` method to generate image caption and extract features.
    3. Call ``respond`` method and generate reply to ``user_question``, this
       also updates the conversation history.
    4. To start a new conversation, call ``set_image`` and pass the new image,
       this also resets all the previous sessions' data and loops back to Step2.

    Attributes
    ----------
    caption_model : ``PythiaCaptioning``
        Captioning model.
    enc_dec_model : ``EncoderDecoderModel``
        Visual Dialog model.
    vocabulary : ``Vocabulary``
        Extracted vocabulary
    config : ``Dict[str, Any]``
        Configurations merged from cmd and config file
    cuda_device : ``torch.device``
        Cuda device where models will be loaded
    add_boundary_toks : ``bool``
        TODO: need this?

    """
    image_feat_list = []
    image_feat_dict = {}
    f = open('image_features_set.json')
    d = json.load(f)
    for arr in d: 
        tensor = torch.tensor(arr[0])
        image_feat_dict[tensor] = True
        image_feat_list.append(tuple(arr[0]))
        image_feat_list.append(arr[1])
    # test = "Testing"
    def __init__(
            self,
            caption_model: DetectCaption,
            enc_dec_model: EncoderDecoderModel,
            vocabulary: Vocabulary,
            config: Dict[str, Any],
            cuda_device: torch.device,
            add_boundary_toks: bool = True,
    ):
        super().__init__()
        self.detect_caption_model = caption_model
        self.enc_dec_model = enc_dec_model
        self.vocabulary = vocabulary
        self.dataset_config = config["dataset"]
        self.caption_config = config["captioning"]
        self.cuda_device = cuda_device
        self.add_boundary_toks = add_boundary_toks
        self.image_features_list = []

        # Initialize class variables
        self.image_features, self.image_caption_nl, self.image_caption = (
            None, None, None
        )
        self.questions, self.question_lengths = [], []
        self.answers, self.answer_lengths = [], []
        self.history, self.history_lengths = [], []
        self.num_rounds = 0

    def _get_data(self, question: Optional[str] = None):
        r""" Build a dict object for inference with the Visdial
        model from natural language question. This is used internally by the
        ``self.respond`` method.

        Parameters
        ----------
        question : ``str``
            Pass the question as raw string.

        Returns
        -------
        Dict[str, torch.Tensor]
            A dictionary object that can be passed to forward method of the
            Visdial model.

        """
        data = {}
        data["img_feat"] = self.image_features

        # only pick the last entry as we process a single question at a time
        data["hist"] = self.history[-1].view(1, 1, -1).long()
        data["hist_len"] = torch.tensor([self.history_lengths[-1]]).long()

        # process the question and fill the inference dict object
        if question is not None:
            question = word_tokenize(question)
            question = self.vocabulary.to_indices(question)
            pad_question, question_length = pad_sequences(
                self.dataset_config,
                self.vocabulary,
                [question]
            )
            data["ques"] = pad_question.view(1, 1, -1).long()
            data["ques_len"] = torch.tensor(question_length).long()

        ans_in = torch.tensor([self.vocabulary.SOS_INDEX]).long()
        data["ans_in"] = ans_in.view(1, 1, -1)

        return data

    def _update(
            self,
            question: Optional[str] = None,
            answer: Optional[str] = None,
    ):
        r""" Update the conversation history with the latest dialog
        (que-ans pair). This is used internally by the ``self.respond`` method.

        Parameters
        ----------
        question : ``str``
            Pass the question as raw string.
        answer: ``str``
            Pass the answer as raw string.

        """
        

        if question is not None:
            question = word_tokenize(question)
            question = self.vocabulary.to_indices(question)
            self.questions.append(question)
            self.question_lengths.append(len(question))

        if answer is not None:
            print('Dialog history answer: ',answer)
            answer = word_tokenize(answer)
            answer = self.vocabulary.to_indices(answer)
            self.answers.append(answer)
            self.answer_lengths.append(len(answer))

        # history does not take in padded inputs! 
        self.history, self.history_lengths = get_history(
            self.dataset_config,
            self.vocabulary,
            self.image_caption,
            self.questions,
            self.answers,
            False
        )
        self.num_rounds += 1

    def _reset(self):
        r""" Delete all the data of the current conversation.  This is used
        internally by the ``self.set_image`` method.

        """
        self.image_features, self.image_caption_nl, self.image_caption = (
            None, None, None
        )
        self.questions, self.question_lengths = [], []
        self.answers, self.answer_lengths = [], []
        self.history, self.history_lengths = [], []
        self.num_rounds = 0

    def set_image(self, image_path):
        r""" Build a dict object for inference inside the Visdial
        model. This is used internally by the ``respond`` method.

        Parameters
        ----------
        question : ``str``
            Pass the question as raw string.

        Returns
        -------
        Dict[str, torch.Tensor]
            A dictionary object that can be passed to forward method of the
            Visdial model.

        """

        self._reset()
        if not os.path.isabs(image_path) and not validate_url(image_path):
            image_path = os.path.abspath(image_path)
        print(f"Loading image from : {image_path}")
        caption_tokens, image_features = self.detect_caption_model.predict(
            image_path,
            self.caption_config["detectron_model"]["feat_name"],
            True,
        )

        if self.dataset_config["img_norm"]:
            image_features = normalize(image_features, dim=0, p=2)

        self.image_caption_nl = \
        self.detect_caption_model.caption_processor(
            caption_tokens.tolist()[0]
        )["caption"]
        self.image_caption = self.vocabulary.to_indices(
            word_tokenize(self.image_caption_nl))
        self.image_features = image_features.unsqueeze(0)
        # build the initial history
        self._update()

    def set_image_condition(self, image_path, path_name=''):
        r""" Build a dict object for inference inside the Visdial
        model. This is used internally by the ``respond`` method.

        Parameters
        ----------
        question : ``str``
            Pass the question as raw string.

        Returns
        -------
        Dict[str, torch.Tensor]
            A dictionary object that can be passed to forward method of the
            Visdial model.

        """

        self._reset()
        if not os.path.isabs(image_path) and not validate_url(image_path):
            image_path = os.path.abspath(image_path)
        print(f"Loading image from : {image_path}")
        caption_tokens, image_features = self.detect_caption_model.predict(
            image_path,
            self.caption_config["detectron_model"]["feat_name"],
            True,
        )

        self.image_features_dict = {}
        


        if self.dataset_config["img_norm"]:
            image_features = normalize(image_features, dim=0, p=2)

        self.image_caption_nl = \
        self.detect_caption_model.caption_processor(
            caption_tokens.tolist()[0]
        )["caption"]

        self.image_features = image_features.unsqueeze(0)
        print("image features: ",self.image_features.cpu().data)
        
        image_feat_list = self.image_features.cpu().data.numpy().tolist()
        
        
        # if tuple(image_feat_list) in DemoSessionManager.image_feat_list:
        #     index = DemoSessionManager.image_feat_list.index(tuple(image_feat_list))
        #     print("cap: ",DemoSessionManager.image_feat_list[index+1])
        #     self.image_caption_nl = DemoSessionManager.image_feat_list[index+1]
        #     # self.image_caption_nl = "Image added"

        self.image_caption_nl = "in script"
        self.image_features_dict[self.image_features] = True
        print(self.image_features_dict)
        image_dict = {}
        image_dict[1] = 'World'
        
        # jpeg_tensor = tf.image.encode_jpeg(image_tensor)
        # print(jpeg_tensor)
        data_new = image_dict
        # torch.save('torch.txt',self.image_features,'ascii')
        # x_np = np.load("img_f2.npz")
        # # x_np = x_np.f
        # x = [x_np[key] for key in x_np]
        # x = np.array(x)
        # print("type x_np: ", type(x))
        # x_tor = torch.from_numpy(x)
        # x_tor_device = torch.from_numpy(x).to('cuda:0')
        # print('device x_tor',x_tor.device)
        # print('device x_tor_device',x_tor_device.device)
        # print('device image featuires',self.image_features.device)
        # test_file = "image_features/let1xiLvzf0_frame_210.pkl"
        # with open(test_file, 'rb') as infile:
        #     result = pickle.load(infile)
        # img_res = self.image_features.cpu().data.numpy().tolist()
        # if result.tolist() == img_res:  print("true")
        # else: print("false")

        # if x_tor == self.image_features.cpu(): print("is true? ")
        # else: print("is false? ")
                   
        img_f_np = self.image_features.cpu().data.numpy()
        # full_path = "image_features/" + path_name + '.pkl'
        # with open(full_path, 'wb') as outfile:
        #     pickle.dump(img_f_np, outfile, pickle.HIGHEST_PROTOCOL)
        # print("pickle dumped")        

        # print("Img F1: ", img_f_np)
        print("Type Img F1: ", type(img_f_np))
        np.savez("img_f2",img_f_np[0])
        # json.dump(self.image_features.cpu().data.numpy().tolist() ,  codecs.open("file_name.json", 'w', encoding='utf-8'), separators=(',', ':'), sort_keys=True)
        # json.dump([[1,2],[3,4],[5,6]] ,  codecs.open("file_name.json", 'w', encoding='utf-8'), separators=(',', ':'), sort_keys=True)
        # f = open('file_name.json')
        # d = json.load(f)
        img_f = self.image_features.cpu().data.numpy()
        print("type f: ", img_f.ndim)
        print("type f: ", img_f[0].shape)
        # for f in img_f:
        #     print("type f: ", type(f))

        print("Type1: ",type(self.image_features.cpu().data.numpy().tolist()))
        # print("Type2: ",type(d))
        # print("Img F2: ", d == self.image_features.cpu().data.numpy().tolist())
#         pytorch_tensor = torch.tensor(
# [
#   [
#       [0.1, 0.2, 0.3],
#       [0.4, 0.5, 0.6],
#       [0.7, 0.8, 0.9]
#   ],
#   [
#       [1.1, 1.2, 1.3],
#       [1.4, 1.5, 1.6],
#       [1.7, 1.8, 1.9]
#   ]
# ]
# )

        # print('tensor1: ',type(pytorch_tensor))
        print('tensor2: ',type(self.image_features))
        self.image_caption = self.vocabulary.to_indices(
        word_tokenize(self.image_caption_nl))
        # build the initial history
        self._update()

    def get_caption(self):
        r""" Return natural language caption.

        Returns
        -------
        str

        """

        if self.image_caption_nl is not None:
            return self.image_caption_nl
        else:
            raise TypeError("Image caption not found. Make sure set_image is "
                            "called prior to using this command.")

    def respond(self, user_question):
        r""" Takes in natural language user question and returns a natural
        language answer to it.

        Parameters
        ----------
        user_question : ``str``
            Pass the raw question as string.

        Returns
        -------
        str
            Answer to the question in natural language.

        """
        user_question = user_question.replace("?", "").lower() + "?"
        batch = self._get_data(user_question)
        for key in batch:
            batch[key] = batch[key].to(self.cuda_device)

        with torch.no_grad():
            (eos_flag, max_len_flag), output = self.enc_dec_model(batch)
        output = [word_idx.item() for word_idx in output.reshape(-1)]
        answer = self.vocabulary.to_words(output)

        # Throw away the trailing '<EOS>' tokens
        if eos_flag:
            first_eos_idx = answer.index(self.vocabulary.EOS_TOKEN)
            answer = answer[:first_eos_idx]
        print('Received answer: ',answer)
        answer = TreebankWordDetokenizer().detokenize(answer)
        print('Converted answer: ',answer)
        # Update the dialog history and return answer
        self._update(user_question, answer)
        # self._update(user_question, "yes")
        return answer

    def set_condition(self, image_path, human_caption):
        r""" 
        Used for conditioning visual dialog

        """
        if not os.path.isabs(image_path) and not validate_url(image_path):
            image_path = os.path.abspath(image_path)
        print(f"Loading image from : {image_path}")
        caption_tokens, image_features = self.detect_caption_model.predict(
            image_path,
            self.caption_config["detectron_model"]["feat_name"],
            True,
        )

        self.image_features_dict = {}
        # self.image_features_list = []
        
        if self.dataset_config["img_norm"]:
            image_features = normalize(image_features, dim=0, p=2)

        # self.image_caption_nl = \
        # self.detect_caption_model.caption_processor(
        #     caption_tokens.tolist()[0]
        # )["caption"]

        self.image_features = image_features.unsqueeze(0)
        image_features = image_features.unsqueeze(0)
        print("image features: ",self.image_features)
        
        
        # print(image_features_dict)
        image_dict = {}
        image_dict[1] = 'World'
        
        # jpeg_tensor = tf.image.encode_jpeg(image_tensor)
        # print(jpeg_tensor)
        data_new = image_dict
        # torch.save('torch.txt',self.image_features,'ascii')
        # print("Img F1: ",self.image_features.cpu().data.numpy().tolist())
        # json.dump(self.image_features.cpu().data.numpy().tolist() ,  codecs.open("file_name.json", 'w', encoding='utf-8'), separators=(',', ':'), sort_keys=True)
        # f = open('file_name.json')
        # d = json.load(f)
        
        self.image_features_list.append([image_features.cpu().data.numpy().tolist(),human_caption])

        print(self.image_features_list)

    def save_condition(self, file_name = "image_features_set.json"):

        json.dump(self.image_features_list ,  codecs.open(file_name, 'w', encoding='utf-8'), separators=(',', ':'), sort_keys=True)


def validate_url(path: str):
    r""" Check whether passed string is a url.

    Parameters
    ----------
    path : ``str``
        Pass the path as string.

    Returns
    -------
    bool
        True/False corresponding to whether it is a url or not.

    """
    try:
        result = urlparse(path)
        return all([result.scheme, result.netloc, result.path])
    except:
        return False
