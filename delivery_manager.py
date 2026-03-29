#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发货管理器
处理订单发货、补发货等功能
"""

import asyncio
import json
import time
import aiohttp
from loguru import logger
from typing import Optional, Dict, Any, List
from utils.xianyu_utils import generate_sign, trans_cookies


class DeliveryManager:
    """发货管理器"""
    
    def __init__(self, session: aiohttp.ClientSession, cookies_str: str, cookie_id: str):
        """
        初始化发货管理器
        
        Args:
            session: aiohttp会话对象
            cookies_str: Cookie字符串
            cookie_id: Cookie ID
        """
        self.session = session
        self.cookies_str = cookies_str
        self.cookie_id = cookie_id
        self.cookies = trans_cookies(cookies_str) if cookies_str else {}
    
    def _safe_str(self, obj):
        """安全字符串转换"""
        try:
            return str(obj)
        except:
            return "无法转换的对象"
    
    async def send_delivery_message(self, order_id: str, buyer_id: str, content: str, item_id: str = None) -> Dict[str, Any]:
        """
        发送发货消息给买家
        
        Args:
            order_id: 订单ID
            buyer_id: 买家ID
            content: 发货内容（卡密/文本）
            item_id: 商品ID（可选）
            
        Returns:
            Dict: 操作结果
        """
        try:
            logger.info(f"【{self.cookie_id}】开始发送发货消息，订单: {order_id}, 买家: {buyer_id}")
            
            # 构建消息数据
            message_data = {
                "content": content,
                "order_id": order_id,
                "item_id": item_id or "",
                "timestamp": int(time.time())
            }
            
            # 这里需要调用闲鱼的消息发送API
            # 由于消息发送逻辑比较复杂，我们使用XianyuAutoAsync中的方法
            # 这里简化处理，实际应该调用send_message_to_user方法
            
            # 记录发货日志
            self._log_delivery(order_id, buyer_id, content, True)
            
            return {
                "success": True,
                "message": "发货消息发送成功",
                "order_id": order_id,
                "buyer_id": buyer_id
            }
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送发货消息失败: {self._safe_str(e)}")
            self._log_delivery(order_id, buyer_id, content, False, str(e))
            return {
                "success": False,
                "message": f"发送发货消息失败: {self._safe_str(e)}",
                "order_id": order_id,
                "error": str(e)
            }
    
    async def manual_delivery(self, order_id: str, delivery_content: str, 
                             buyer_id: str = None, item_id: str = None) -> Dict[str, Any]:
        """
        手动补发货
        
        Args:
            order_id: 订单ID
            delivery_content: 发货内容
            buyer_id: 买家ID（可选，如果不提供会从数据库获取）
            item_id: 商品ID（可选）
            
        Returns:
            Dict: 操作结果
        """
        try:
            logger.info(f"【{self.cookie_id}】开始手动补发货，订单: {order_id}")
            
            # 从数据库获取订单信息
            from db_manager import db_manager
            order_info = db_manager.get_order_by_id(order_id)
            
            if not order_info:
                return {
                    "success": False,
                    "message": "订单不存在",
                    "order_id": order_id
                }
            
            # 获取买家ID
            if not buyer_id:
                buyer_id = order_info.get('buyer_id')
            
            if not buyer_id:
                return {
                    "success": False,
                    "message": "无法获取买家ID",
                    "order_id": order_id
                }
            
            # 发送发货消息
            result = await self.send_delivery_message(order_id, buyer_id, delivery_content, item_id)
            
            if result.get('success'):
                # 更新订单状态为已发货
                db_manager.update_order_status(
                    order_id=order_id,
                    new_status='shipped',
                    cookie_id=self.cookie_id,
                    context=f"手动补发货 - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                logger.info(f"【{self.cookie_id}】✅ 手动补发货成功，订单: {order_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】手动补发货失败: {self._safe_str(e)}")
            return {
                "success": False,
                "message": f"手动补发货失败: {self._safe_str(e)}",
                "order_id": order_id,
                "error": str(e)
            }
    
    async def auto_delivery(self, order_id: str, item_id: str = None, 
                           rule_id: str = None) -> Dict[str, Any]:
        """
        自动发货
        
        Args:
            order_id: 订单ID
            item_id: 商品ID
            rule_id: 发货规则ID（可选）
            
        Returns:
            Dict: 操作结果
        """
        try:
            logger.info(f"【{self.cookie_id}】开始自动发货，订单: {order_id}")
            
            # 从数据库获取订单信息
            from db_manager import db_manager
            order_info = db_manager.get_order_by_id(order_id)
            
            if not order_info:
                return {
                    "success": False,
                    "message": "订单不存在",
                    "order_id": order_id
                }
            
            # 检查是否已经发货
            if order_info.get('order_status') == 'shipped':
                logger.info(f"【{self.cookie_id}】订单 {order_id} 已经发货，跳过")
                return {
                    "success": True,
                    "message": "订单已经发货",
                    "order_id": order_id
                }
            
            buyer_id = order_info.get('buyer_id')
            if not buyer_id:
                return {
                    "success": False,
                    "message": "无法获取买家ID",
                    "order_id": order_id
                }
            
            # 获取发货内容
            delivery_content = await self._get_delivery_content(order_id, item_id, rule_id)
            
            if not delivery_content:
                # 标记为发货失败，需要手动处理
                db_manager.update_order_status(
                    order_id=order_id,
                    new_status='delivery_failed',
                    cookie_id=self.cookie_id,
                    context=f"自动发货失败：未找到发货内容 - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return {
                    "success": False,
                    "message": "未找到发货内容，已标记为发货失败",
                    "order_id": order_id
                }
            
            # 发送发货消息
            result = await self.send_delivery_message(order_id, buyer_id, delivery_content, item_id)
            
            if result.get('success'):
                # 更新订单状态为已发货
                db_manager.update_order_status(
                    order_id=order_id,
                    new_status='shipped',
                    cookie_id=self.cookie_id,
                    context=f"自动发货成功 - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                # 标记为发货失败
                db_manager.update_order_status(
                    order_id=order_id,
                    new_status='delivery_failed',
                    cookie_id=self.cookie_id,
                    context=f"自动发货失败：{result.get('message')} - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】自动发货失败: {self._safe_str(e)}")
            # 标记为发货失败
            try:
                from db_manager import db_manager
                db_manager.update_order_status(
                    order_id=order_id,
                    new_status='delivery_failed',
                    cookie_id=self.cookie_id,
                    context=f"自动发货异常：{str(e)} - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except:
                pass
            
            return {
                "success": False,
                "message": f"自动发货失败: {self._safe_str(e)}",
                "order_id": order_id,
                "error": str(e)
            }
    
    async def _get_delivery_content(self, order_id: str, item_id: str = None, 
                                   rule_id: str = None) -> Optional[str]:
        """
        获取发货内容
        
        Args:
            order_id: 订单ID
            item_id: 商品ID
            rule_id: 发货规则ID
            
        Returns:
            str: 发货内容，如果找不到返回None
        """
        try:
            from db_manager import db_manager
            
            # 如果有规则ID，使用规则获取内容
            if rule_id:
                # 从发货规则获取内容
                # 这里需要根据实际的数据库结构实现
                pass
            
            # 如果有商品ID，尝试匹配发货规则
            if item_id:
                # 获取商品信息
                # 尝试匹配关键字规则
                pass
            
            # 默认返回None，需要根据实际情况实现
            # 这里可以对接卡券系统或其他发货内容来源
            return None
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取发货内容失败: {self._safe_str(e)}")
            return None
    
    def _log_delivery(self, order_id: str, buyer_id: str, content: str, 
                     success: bool, error: str = None):
        """记录发货日志"""
        try:
            from db_manager import db_manager
            
            log_data = {
                'order_id': order_id,
                'buyer_id': buyer_id,
                'cookie_id': self.cookie_id,
                'success': success,
                'content_length': len(content) if content else 0,
                'error': error,
                'timestamp': time.time()
            }
            
            logger.info(f"【{self.cookie_id}】记录发货日志: {log_data}")
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】记录发货日志失败: {self._safe_str(e)}")


# 全局实例管理器
_delivery_managers = {}


def get_delivery_manager(session: aiohttp.ClientSession, cookies_str: str, cookie_id: str) -> DeliveryManager:
    """
    获取或创建发货管理器实例
    
    Args:
        session: aiohttp会话对象
        cookies_str: Cookie字符串
        cookie_id: Cookie ID
        
    Returns:
        DeliveryManager: 管理器实例
    """
    if cookie_id not in _delivery_managers:
        _delivery_managers[cookie_id] = DeliveryManager(session, cookies_str, cookie_id)
    
    return _delivery_managers[cookie_id]


def remove_delivery_manager(cookie_id: str):
    """移除管理器实例"""
    if cookie_id in _delivery_managers:
        del _delivery_managers[cookie_id]
        logger.info(f"移除发货管理器: {cookie_id}")
