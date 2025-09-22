# 异步版本: pip install motor
# pip install pymongo

import os
from typing import Dict, Any, Optional, List

import motor.motor_asyncio
from bson import ObjectId


class AsyncMongoDBClient:
    def __init__(self, db_name, connection_string=None):
        if not connection_string:
            connection_string = os.getenv("MONGO_DB_CONN_STR")
        self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
        self.db = self.client[db_name]

    async def insert_one(self, collection_name: str, document: Dict[str, Any]) -> Optional[ObjectId]:
        """异步插入单个文档"""
        try:
            result = await self.db[collection_name].insert_one(document)
            return result.inserted_id
        except Exception as e:
            print(f"插入失败: {e}")
            return None

    async def find_one(self, collection_name: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """异步查询单个文档"""
        try:
            return await self.db[collection_name].find_one(query)
        except Exception as e:
            print(f"查询失败: {e}")
            return None

    async def find_many(self, collection_name: str, query: Dict[str, Any] = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
        """异步查询多个文档"""
        if query is None:
            query = {}
        try:
            cursor = self.db[collection_name].find(query).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            print(f"查询失败: {e}")
            return []

    async def update_one(self, collection_name: str, query: Dict[str, Any],
                         update_data: Dict[str, Any]) -> bool:
        """异步更新单个文档"""
        try:
            result = await self.db[collection_name].update_one(query, {'$set': update_data})
            return result.modified_count > 0
        except Exception as e:
            print(f"更新失败: {e}")
            return False

    async def delete_one(self, collection_name: str, query: Dict[str, Any]) -> bool:
        """异步删除单个文档"""
        try:
            result = await self.db[collection_name].delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            print(f"删除失败: {e}")
            return False
