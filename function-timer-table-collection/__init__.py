import json
import logging
import random
from datetime import datetime
from typing import Optional
import random
import azure.functions as func
from azure.core.paging import ItemPaged
from azure.data.tables import TableClient, TableEntity
from praw.models import Submission, Comment

from shared_code.helpers.reddit_helper import RedditManager
from shared_code.helpers.tagging import TaggingMixin
from shared_code.storage_proxies.service_proxy import QueueServiceProxy
from shared_code.storage_proxies.table_proxy import TableServiceProxy, TableRecord
from shared_code.models.bot_configuration import BotConfigurationManager, BotConfiguration


def main(tableTimer: func.TimerRequest) -> None:
	proxy: TableServiceProxy = TableServiceProxy()

	queue_proxy: QueueServiceProxy = QueueServiceProxy()

	helper: RedditManager = RedditManager()

	client: TableClient = proxy.get_client()

	bot_config_manager: BotConfigurationManager = BotConfigurationManager()

	bot_config: BotConfiguration = random.choice(bot_config_manager.configurations)

	submission_workers = ["worker-1"]
	comment_workers = ["worker-2", "worker-3"]

	query_string = f"has_responded eq false and input_type eq 'Submission' and text_generation_prompt eq '' and responding_bot eq '{bot_config.Name}'"

	pending_submissions: ItemPaged[TableEntity] = client.query_entities(query_string, results_per_page=10)
	submission_results = []

	for pages in pending_submissions.by_page():
		for page in pages:
			record: TableRecord = json.loads(json.dumps(page), object_hook=lambda d: TableRecord(**d))
			e = client.get_entity(partition_key=record.PartitionKey, row_key=record.RowKey)
			client.update_entity(e)
			submission_results.append(record)
		break

	for record in submission_results:
		processed = process_input(helper, record)
		record.text_generation_prompt = processed
		queue = queue_proxy.service.get_queue_client(random.choice(submission_workers))
		queue.send_message(record.json)

	comment_results = []
	query_string = f"has_responded eq false and input_type eq 'Comment' and text_generation_prompt eq '' and responding_bot eq '{bot_config.Name}'"
	pending_comments: ItemPaged[TableEntity] = client.query_entities(query_string, results_per_page=10)

	for pages in pending_comments.by_page():
		for page in pages:
			record: TableRecord = json.loads(json.dumps(page), object_hook=lambda d: TableRecord(**d))
			comment_results.insert(0, record)
			e = client.get_entity(partition_key=record.PartitionKey, row_key=record.RowKey)
			client.update_entity(e)
		break

	for record in comment_results:
		processed = process_input(helper, record)
		record.text_generation_prompt = processed
		queue = queue_proxy.service.get_queue_client(random.choice(comment_workers))
		queue.send_message(record.json)


def process_input(helper: RedditManager, incoming_message: TableRecord) -> Optional[str]:
	tagging_mixin = TaggingMixin()
	instance = helper.get_praw_instance_for_bot(incoming_message.responding_bot)

	if incoming_message.input_type == "Submission":
		thing: Submission = instance.submission(id=incoming_message.id)
		history = tagging_mixin.collate_tagged_comment_history(thing)
		cleaned_history = tagging_mixin.remove_username_mentions_from_string(history, incoming_message.responding_bot)
		reply_start_tag = tagging_mixin.get_reply_tag(thing, incoming_message.responding_bot)
		prompt = cleaned_history + reply_start_tag
		return prompt

	if incoming_message.input_type == "Comment":
		thing = instance.comment(id=incoming_message.id)
		history = tagging_mixin.collate_tagged_comment_history(thing)
		cleaned_history = tagging_mixin.remove_username_mentions_from_string(history, incoming_message.responding_bot)
		reply_start_tag = tagging_mixin.get_reply_tag(thing, incoming_message.responding_bot)
		prompt = cleaned_history + reply_start_tag
		return prompt


def timestamp_to_hours(utc_timestamp):
	return (datetime.utcnow() - datetime.fromtimestamp(utc_timestamp)).total_seconds() / 3600