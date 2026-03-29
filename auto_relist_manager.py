#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动重新上架管理器
当商品成交后，自动将商品重新上架
"""

import asyncio
import json
import time
import aiohttp
from loguru import logger
from typing import Optional, Dict, Any
from utils.xianyu_utils import generate_sign, trans_cookies


class AutoRelistManager:
    """自动重新上架管理器"""
    
    def __init__(self, session: aiohttp.ClientSession, cookies_str: str, cookie_id: str):
        """
        初始化自动重新上架管理器
        
        Args:
            session: aiohttp会话对象
            cookies_str: Cookie字符串
            cookie_id: Cookie ID
        """
        self.session = session
        self.cookies_str = cookies_str
        self.cookie_id = cookie_id
        self.cookies = trans_cookies(cookies_str) if cookies_str else {}
        
        # 记录已处理的订单，避免重复上架
        self._processed_orders = {}
        
    def _safe_str(self, obj):
        """安全字符串转换"""
        try:
            return str(obj)
        except:
            return "无法转换的对象"
    
    async def relist_item(self, item_id: str, order_id: str = None) -> Dict[str, Any]:
        """
        重新上架商品
        
        Args:
            item_id: 商品ID
            order_id: 订单ID（可选，用于记录）
            
        Returns:
            Dict: 操作结果
        """
        try:
            # 检查是否已经处理过这个订单
            if order_id and order_id in self._processed_orders:
                logger.info(f"【{self.cookie_id}】订单 {order_id} 已经处理过重新上架，跳过")
                return {"success": True, "message": "已经处理过", "item_id": item_id}
            
            logger.info(f"【{self.cookie_id}】开始重新上架商品: {item_id}")
            
            # 构建API请求参数
            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': str(int(time.time()) * 1000),
                'sign': '',
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idle.item.relist',
                'sessionOption': 'AutoLoginOnly',
            }
            
            # 构建请求数据
            data_val = json.dumps({"itemId": item_id})
            data = {'data': data_val}
            
            # 生成签名
            token = self.cookies.get('_m_h5_tk', '').split('_')[0] if self.cookies.get('_m_h5_tk') else ''
            sign = generate_sign(params['t'], token, data_val)
            params['sign'] = sign
            
            # 发送请求
            async with self.session.post(
                'https://h5api.m.goofish.com/h5/mtop.taobao.idle.item.relist/1.0/',
                params=params,
                data=data
            ) as response:
                res_json = await response.json()
                
                # 检查并更新Cookie
                if 'set-cookie' in response.headers:
                    new_cookies = {}
                    for cookie in response.headers.getall('set-cookie', []):
                        if '=' in cookie:
                            name, value = cookie.split(';')[0].split('=', 1)
                            new_cookies[name.strip()] = value.strip()
                    
                    if new_cookies:
                        self.cookies.update(new_cookies)
                        self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                
                # 解析响应
                if res_json.get('ret') and res_json['ret'][0] == 'SUCCESS::调用成功':
                    logger.info(f"【{self.cookie_id}】✅ 商品重新上架成功: {item_id}")
                    
                    # 记录已处理的订单
                    if order_id:
                        self._processed_orders[order_id] = {
                            'item_id': item_id,
                            'time': time.time()
                        }
                    
                    return {
                        "success": True,
                        "message": "重新上架成功",
                        "item_id": item_id,
                        "data": res_json.get('data', {})
                    }
                else:
                    error_msg = res_json.get('ret', ['未知错误'])[0] if res_json.get('ret') else '未知错误'
                    logger.error(f"【{self.cookie_id}】❌ 商品重新上架失败: {error_msg}")
                    
                    return {
                        "success": False,
                        "message": f"重新上架失败: {error_msg}",
                        "item_id": item_id,
                        "error": error_msg
                    }
                    
        except Exception as e:
            logger.error(f"【{self.cookie_id}】重新上架商品时出错: {self._safe_str(e)}")
            return {
                "success": False,
                "message": f"重新上架出错: {self._safe_str(e)}",
                "item_id": item_id,
                "error": str(e)
            }
    
    async def handle_order_completed(self, order_id: str, item_id: str = None) -> Dict[str, Any]:
        """
        处理订单完成事件，自动重新上架商品
        
        Args:
            order_id: 订单ID
            item_id: 商品ID（如果已知）
            
        Returns:
            Dict: 操作结果
        """
        try:
            logger.info(f"【{self.cookie_id}】处理订单完成事件: {order_id}")
            
            # 如果没有提供item_id，尝试从数据库获取
            if not item_id:
                from db_manager import db_manager
                order_info = db_manager.get_order_by_id(order_id)
                if order_info and order_info.get('item_id'):
                    item_id = order_info['item_id']
                    logger.info(f"【{self.cookie_id}】从数据库获取到商品ID: {item_id}")
                else:
                    logger.warning(f"【{self.cookie_id}】无法获取订单 {order_id} 的商品ID")
                    return {
                        "success": False,
                        "message": "无法获取商品ID",
                        "order_id": order_id
                    }
            
            # 执行重新上架
            result = await self.relist_item(item_id, order_id)
            
            # 记录到数据库
            self._log_relist_event(order_id, item_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理订单完成事件时出错: {self._safe_str(e)}")
            return {
                "success": False,
                "message": f"处理订单完成事件出错: {self._safe_str(e)}",
                "order_id": order_id,
                "error": str(e)
            }
    
    def _log_relist_event(self, order_id: str, item_id: str, result: Dict[str, Any]):
        """记录重新上架事件到数据库"""
        try:
            from db_manager import db_manager
            
            # 构建日志数据
            log_data = {
                'order_id': order_id,
                'item_id': item_id,
                'cookie_id': self.cookie_id,
                'success': result.get('success', False),
                'message': result.get('message', ''),
                'timestamp': time.time()
            }
            
            # 插入到数据库（如果有相关表）
            # 这里可以根据需要创建专门的表来记录重新上架日志
            logger.info(f"【{self.cookie_id}】记录重新上架事件: {log_data}")
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】记录重新上架事件失败: {self._safe_str(e)}")
    
    async def batch_relist_items(self, item_ids: list) -> Dict[str, Any]:
        """
        批量重新上架商品
        
        Args:
            item_ids: 商品ID列表
            
        Returns:
            Dict: 批量操作结果
        """
        results = {
            "success": [],
            "failed": [],
            "total": len(item_ids)
        }
        
        for item_id in item_ids:
            result = await self.relist_item(item_id)
            if result.get('success'):
                results["success"].append(item_id)
            else:
                results["failed"].append({
                    "item_id": item_id,
                    "error": result.get('message', '未知错误')
                })
            
            # 添加延迟，避免请求过快
            await asyncio.sleep(random.uniform(1, 3))
        
        logger.info(f"【{self.cookie_id}】批量重新上架完成: 成功 {len(results['success'])}/{len(item_ids)}")
        return results


# 全局实例管理器
_auto_relist_managers = {}


def get_auto_relist_manager(session: aiohttp.ClientSession, cookies_str: str, cookie_id: str) -> AutoRelistManager:
    """
    获取或创建自动重新上架管理器实例
    
    Args:
        session: aiohttp会话对象
        cookies_str: Cookie字符串
        cookie_id: Cookie ID
        
    Returns:
        AutoRelistManager: 管理器实例
    """
    if cookie_id not in _auto_relist_managers:
        _auto_relist_managers[cookie_id] = AutoRelistManager(session, cookies_str, cookie_id)
    
    return _auto_relist_managers[cookie_id]


def remove_auto_relist_manager(cookie_id: str):
    """移除管理器实例"""
    if cookie_id in _auto_relist_managers:
        del _auto_relist_managers[cookie_id]
        logger.info(f"移除自动重新上架管理器: {cookie_id}")
