import logging
import base64
import json
import logging

import azure.functions as func
from azure.data.tables import TableClient, TableEntity, TableServiceClient
from azure.storage.queue import QueueServiceClient, QueueClient, QueueMessage
from praw import Reddit
from praw.models import Submission, Comment

from shared_code.helpers.reddit_helper import RedditManager
from shared_code.helpers.tagging import TaggingMixin
from shared_code.models.table_data import TableRecord
from shared_code.storage_proxies.service_proxy import QueueServiceProxy
from shared_code.storage_proxies.table_proxy import TableServiceProxy


def main(replyTimer: func.TimerRequest) -> None:
	tagging: TaggingMixin = TaggingMixin()
	queue_service: QueueServiceClient = QueueServiceProxy().service
	table_service: TableServiceClient = TableServiceProxy().service
	helper: RedditManager = RedditManager()

	queue_client: QueueClient = queue_service.get_queue_client("reply-queue")

	table_client: TableClient = table_service.get_table_client("tracking")

	if len(queue_client.peek_messages()) == 0:
		logging.debug(":: No New Messages")
		return None

	message: QueueMessage = queue_client.receive_message()

	queue_client.delete_message(message)

	queue_client.close()

	record: TableRecord = handle_incoming_message(message)

	prompt: str = record.text_generation_prompt

	response: str = record.text_generation_response

	extract: dict = tagging.extract_reply_from_generated_text(prompt, response)

	reddit: Reddit = helper.get_praw_instance_for_bot(bot_name=record.responding_bot)

	entity: TableEntity = table_client.get_entity(record.PartitionKey, record.RowKey)

	if not extract['body']:
		logging.info(":: No Body Present")
		table_client.close()
		return

	if record.input_type == "Submission":
		sub_instance: Submission = reddit.submission(id=record.id)
		sub_instance.reply(extract['body'])
		entity["has_responded"] = True
		table_client.update_entity(entity)
		logging.info(f"{record.responding_bot} - {record.input_type} - {extract['body']}")

	if record.input_type == "Comment":
		comment_instance: Comment = reddit.comment(id=record.id)
		comment_instance.reply(extract['body'])
		entity["has_responded"] = True
		table_client.update_entity(entity)
		logging.info(f"{record.responding_bot} - {record.input_type} - {extract['body']}")

	table_client.close()


def handle_incoming_message(message) -> TableRecord:
	try:
		incoming_message: TableRecord = json.loads(base64.b64decode(message.content), object_hook=lambda d: TableRecord(**d))
		return incoming_message
	except Exception:
		incoming_message: TableRecord = json.loads(message.content, object_hook=lambda d: TableRecord(**d))
		return incoming_message