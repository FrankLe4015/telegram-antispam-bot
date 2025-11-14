#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import time
import threading
from datetime import datetime

from telegram import Update, ChatMember
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 关键词数据文件
KEYWORDS_FILE = 'keywords.json'

# 管理员缓存
admin_cache = {}
CACHE_DURATION = 300

class AntiSpamBot:
    def __init__(self):
        self.keywords_data = self.load_keywords()
        
    def load_keywords(self):
        """加载关键词数据"""
        try:
            if os.path.exists(KEYWORDS_FILE):
                with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载关键词文件失败: {e}")
        
        return {
            "gambling": [
                "赌博", "博彩", "百家乐", "德州扑克", "老虎机", 
                "充值", "提现", "返水", "洗码", "上分", "下分",
                "AG亚游", "BBIN", "沙巴", "皇冠", "永利",
                "一夜暴富", "稳赚不赔", "日赚千元", "网投", "网赌",
            ],
            "adult": [
                "约炮", "援交", "包养", "小姐", "嫖娼",
                "黄色", "成人", "情色", "三级", "av",
                "性服务", "上门服务", "特殊服务",
                "一夜情", "找乐子", "寂寞",
            ],
            "custom": []
        }
    
    def save_keywords(self):
        """保存关键词到文件"""
        try:
            with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.keywords_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存关键词文件失败: {e}")
            return False
    
    def get_all_keywords(self):
        """获取所有关键词"""
        all_keywords = []
        for category, keywords in self.keywords_data.items():
            all_keywords.extend(keywords)
        return all_keywords
    
    def add_keyword(self, keyword, category="custom"):
        """添加关键词"""
        if category not in self.keywords_data:
            self.keywords_data[category] = []
        
        if keyword not in self.keywords_data[category]:
            self.keywords_data[category].append(keyword)
            return self.save_keywords()
        return False
    
    def remove_keyword(self, keyword):
        """删除关键词"""
        for category, keywords in self.keywords_data.items():
            if keyword in keywords:
                keywords.remove(keyword)
                return self.save_keywords()
        return False
    
    def check_spam(self, text):
        """检查文本是否为垃圾信息"""
        if not text:
            return False, None
            
        text = text.strip().lower()
        all_keywords = self.get_all_keywords()
        
        for keyword in all_keywords:
            if keyword.lower() in text:
                return True, keyword
        return False, None

# 创建全局bot实例
bot_instance = AntiSpamBot()

def is_admin(update, user_id):
    """检查用户是否为群组管理员"""
    try:
        chat_id = update.effective_chat.id
        cache_key = f"{chat_id}_{user_id}"
        current_time = time.time()
        
        # 检查缓存
        if cache_key in admin_cache:
            cache_time, is_admin_cached = admin_cache[cache_key]
            if current_time - cache_time < CACHE_DURATION:
                return is_admin_cached
        
        # 获取用户权限
        member = update.message.bot.get_chat_member(chat_id, user_id)
        is_admin_result = member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        
        # 更新缓存
        admin_cache[cache_key] = (current_time, is_admin_result)
        
        return is_admin_result
        
    except Exception as e:
        logger.error(f"检查管理员权限失败: {e}")
        return False

def admin_required(func):
    """管理员权限装饰器"""
    def wrapper(update, context):
        if is_admin(update, update.effective_user.id):
            return func(update, context)
        else:
            update.message.reply_text("❌ 此命令仅限群组管理员使用")
    return wrapper

def start(update, context):
    """启动命令"""
    welcome_text = """🤖 反垃圾机器人已启动！

📝 管理员命令：
• /add <关键词> - 添加关键词
• /delete <关键词> - 删除关键词  
• /list - 查看关键词列表
• /stats - 查看统计信息

⚡ 功能：
• 自动检测并删除垃圾/广告信息
• 支持博彩、色情内容过滤

💡 使用说明：
请确保机器人有删除消息的管理员权限"""
    
    update.message.reply_text(welcome_text)

@admin_required
def add_keyword_command(update, context):
    """添加关键词命令"""
    if not context.args:
        update.message.reply_text("❌ 请提供要添加的关键词\n用法: /add <关键词>")
        return
    
    keyword = ' '.join(context.args)
    if bot_instance.add_keyword(keyword):
        update.message.reply_text(f"✅ 已添加关键词: {keyword}")
    else:
        update.message.reply_text(f"❌ 关键词已存在: {keyword}")

@admin_required  
def delete_keyword_command(update, context):
    """删除关键词命令"""
    if not context.args:
        update.message.reply_text("❌ 请提供要删除的关键词\n用法: /delete <关键词>")
        return
    
    keyword = ' '.join(context.args)
    if bot_instance.remove_keyword(keyword):
        update.message.reply_text(f"✅ 已删除关键词: {keyword}")
    else:
        update.message.reply_text(f"❌ 未找到关键词: {keyword}")

@admin_required
def list_keywords_command(update, context):
    """列出所有关键词命令"""
    keywords_data = bot_instance.keywords_data
    
    if not any(keywords_data.values()):
        update.message.reply_text("📝 关键词列表为空")
        return
    
    message_parts = ["📝 当前关键词列表:\n"]
    
    for category, keywords in keywords_data.items():
        if keywords:
            category_name = {
                "gambling": "🎰 博彩类",
                "adult": "🔞 成人类", 
                "custom": "⚙️ 自定义"
            }.get(category, f"📂 {category}")
            
            message_parts.append(f"\n{category_name}:")
            for i, keyword in enumerate(keywords[:10], 1):
                message_parts.append(f"{i}. {keyword}")
            
            if len(keywords) > 10:
                message_parts.append(f"... 还有{len(keywords) - 10}个关键词")
    
    response = '\n'.join(message_parts)
    if len(response) > 4000:
        response = response[:4000] + "\n\n... (消息过长，已截断)"
    
    update.message.reply_text(response)

@admin_required
def stats_command(update, context):
    """统计信息命令"""
    keywords_data = bot_instance.keywords_data
    total_keywords = sum(len(keywords) for keywords in keywords_data.values())
    
    stats_text = f"""📊 机器人统计信息

🔢 关键词总数: {total_keywords}
• 🎰 博彩类: {len(keywords_data.get('gambling', []))}
• 🔞 成人类: {len(keywords_data.get('adult', []))}  
• ⚙️ 自定义: {len(keywords_data.get('custom', []))}

📅 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🟢 状态: 运行正常"""
    
    update.message.reply_text(stats_text)

def message_handler(update, context):
    """消息处理器 - 检查垃圾信息"""
    if not update.message or not update.message.text:
        return
    
    # 忽略群组管理员的消息
    if is_admin(update, update.effective_user.id):
        return
    
    message_text = update.message.text
    is_spam, matched_keyword = bot_instance.check_spam(message_text)
    
    if is_spam:
        try:
            # 删除垃圾消息
            update.message.delete()
            
            # 发送通知
            chat = update.effective_chat
            warning_msg = chat.send_message(f"🗑️ 已删除垃圾信息 (匹配: {matched_keyword})")
            
            # 5秒后删除警告消息
            def delete_warning():
                time.sleep(5)
                try:
                    warning_msg.delete()
                except:
                    pass
            
            threading.Thread(target=delete_warning, daemon=True).start()
                
            logger.info(f"删除垃圾消息: {message_text[:50]}... (匹配: {matched_keyword})")
            
        except Exception as e:
            logger.error(f"删除消息失败: {e}")

def health_check(update, context):
    """健康检查端点"""
    update.message.reply_text("🟢 Bot运行正常")

def main():
    """主函数"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("未找到TELEGRAM_BOT_TOKEN环境变量")
        return
    
    try:
        updater = Updater(token=token, use_context=True)
        dispatcher = updater.dispatcher
        
        # 添加命令处理器
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("add", add_keyword_command))
        dispatcher.add_handler(CommandHandler("delete", delete_keyword_command))
        dispatcher.add_handler(CommandHandler("list", list_keywords_command))
        dispatcher.add_handler(CommandHandler("stats", stats_command))
        dispatcher.add_handler(CommandHandler("health", health_check))
        
        # 添加消息处理器
        dispatcher.add_handler(MessageHandler(
            Filters.text & Filters.chat_type.groups,
            message_handler
        ))
        
        logger.info("🤖 反垃圾机器人启动成功!")
        logger.info(f"📝 当前关键词总数: {sum(len(keywords) for keywords in bot_instance.keywords_data.values())}")
        
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        logger.error(f"Bot启动失败: {e}")
        raise

if __name__ == '__main__':
    main()
