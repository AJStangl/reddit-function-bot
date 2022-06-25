import json
import logging
import urllib.parse
from collections import OrderedDict

import nltk
import requests
from bs4 import BeautifulSoup
from nltk import sent_tokenize, TweetTokenizer

from shared_code.helpers.tagging import TaggingMixin


class ImageScrapper:
	def __init__(self):
		self.default_image_generation_parameters = {
		'type': 'scraper',
		'prompt': None,
		'image_post_search_prefix': None}
		self.tagging: TaggingMixin = TaggingMixin()

	def get_image_post(self, bot_username, generated_text):
		new_prompt = self.tagging.extract_title_from_generated_text(generated_text)
		image_url = self._download_image_for_search_string(bot_username, new_prompt)
		return image_url

	def _download_image_for_search_string(self, bot_username, prompt):
		logging.info(f"{bot_username} is searching on Bing for an image..")

		first_sentence = sent_tokenize(prompt)[0]
		tokenized = TweetTokenizer().tokenize(first_sentence.translate({ord(ch): None for ch in '0123456789'}))
		tokenized = [i for i in tokenized if len(i) > 1]
		tokenized = list(OrderedDict.fromkeys(tokenized))
		pos_tagged_text = nltk.pos_tag(tokenized)

		prompt_keywords = [i[0] for i in pos_tagged_text if i[1][:2] in ['NN', 'VB', 'RB']]

		# Hack
		search_prefix_keywords = []
		search_keywords = search_prefix_keywords + prompt_keywords[:(10 - len(search_prefix_keywords))]

		search_keywords_as_string = ' '.join(search_keywords)

		search_parameters = {'q': search_keywords_as_string, 'form': 'HDRSC2', 'safeSearch': 'strict', 'first': int(1 + (1 * 10))}

		encoded_search_parameters = urllib.parse.urlencode(search_parameters)

		search_url = "https://www.bing.com/images/search?" + encoded_search_parameters

		logging.info(f"Searching for an image with url: {search_url}")

		# Use Win10 Edge User Agent
		header = {
			'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36 Edg/92.0.902.78"}

		r = requests.get(search_url, headers=header)

		if r.ok:
			soup = BeautifulSoup(r.text, 'html.parser')
			link_results = soup.find_all("a", {"class": "iusc"})

			for link in link_results[:10]:
				if link.has_attr('m'):
					# convert json in the link's attributes into a python dict
					m = json.loads(link["m"])
					if 'murl' in m:
						image_url = m['murl']
						return image_url