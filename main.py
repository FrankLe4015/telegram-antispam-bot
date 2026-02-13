#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import asyncio
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# 手动创建 imghdr 模块来解决依赖问题
import sys
import types

def create_imghdr_module():
    """手动创建 imghdr 模块"""
    imghdr = types.ModuleType('imghdr')
    
    def what(file, h=None):
        """返回 None，满足基本接口需求"""
        return None
    
    imghdr.what = what
    sys.modules['imghdr'] = imghdr
    return imghdr

# 确保 imghdr 模块存在
try:
    import imghdr
except ImportError:
    imghdr = create_imghdr_module()

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Simple HTTP handler for health checks
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')
    
    def log_message(self, format, *args):
        # Suppress HTTP request logs
        pass

def start_http_server():
    """Start HTTP server for Render health checks"""
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"HTTP server started on port {port}")
    server.serve_forever()

def keep_alive():
    """Keep the service alive by pinging itself every 10 minutes"""
    # Get the service URL from environment or construct it
    service_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://telegram-antispam-bot-7ewc.onrender.com')
    
    while True:
        try:
            time.sleep(600)  # Wait 10 minutes
            with urllib.request.urlopen(service_url, timeout=30) as response:
                if response.getcode() == 200:
                    logger.info("✅ Keep-alive ping successful")
                else:
                    logger.warning(f"⚠️ Keep-alive ping returned status {response.getcode()}")
        except urllib.error.URLError as e:
            logger.error(f"❌ Keep-alive ping failed: {e}")
        except Exception as e:
            logger.error(f"❌ Keep-alive ping failed: {e}")

def start_keep_alive():
    """Start keep-alive in a separate thread"""
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    logger.info("🔄 Keep-alive service started")

# Keywords data file
KEYWORDS_FILE = 'keywords.json'

# Admin cache
admin_cache = {}
CACHE_DURATION = 300

class AntiSpamBot:
    def __init__(self):
        self.keywords_data = self.load_keywords()
        
    def load_keywords(self):
        """Load keywords data"""
        try:
            if os.path.exists(KEYWORDS_FILE):
                with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load keywords file: {e}")
        
        return {
            "gambling": [
                "赌博", "博彩", "百家乐", "德州扑克", "老虎机", 
                "充值", "提现", "返水", "洗码", "上分", "下分",
                "AG亚游", "BBIN", "沙巴", "皇冠", "永利",
                "一夜暴富", "稳赚不赔", "日赚千元", "网投", "网赌",

            ],
            "crypto_scam": [
                "代币", "虚拟币", "数字货币", "加密货币",
                "USDT", "泰达币", "比特币", "BTC", "ETH", "以太坊",
                "合约", "合约地址", "钱包", "助记词", "私钥",
                "空投", "白 沙", "一级市场", "私募",
                "搬砖", "套利", "高息", "开盒", "矿机",
                "交易所", "U商", "收U", "出U","看盘","日结","666","看盘","連勝","重大勁爆","勁爆","喷水","头像",
            ],
            "adult": [
                "约炮", "援交", "包养", "小姐", "嫖娼",
                "黄色", "成人", "情色", "三级", "av",
                "性服务", "上门服务", "特殊服务",
                "一夜情", "找乐子", "寂寞","私密","哟","you","转移","色情","偷拍","劲爆","🔞","社工库","炸裂","简介"
            ],
            "custom": []
        }
    
    def save_keywords(self):
        """Save keywords to file"""
        try:
            with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.keywords_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save keywords file: {e}")
            return False
    
    def get_all_keywords(self):
        """Get all keywords"""
        all_keywords = []
        for category, keywords in self.keywords_data.items():
            all_keywords.extend(keywords)
        return all_keywords
    
    def add_keyword(self, keyword, category="custom"):
        """Add keyword"""
        if category not in self.keywords_data:
            self.keywords_data[category] = []
        
        if keyword not in self.keywords_data[category]:
            self.keywords_data[category].append(keyword)
            return self.save_keywords()
        return False
    
    def remove_keyword(self, keyword):
        """Remove keyword"""
        for category, keywords in self.keywords_data.items():
            if keyword in keywords:
                keywords.remove(keyword)
                return self.save_keywords()
        return False
    
    def check_spam(self, text):
        """Check if text is spam"""
        if not text:
            return False, None
            
        text = text.strip().lower()
        all_keywords = self.get_all_keywords()
        
        for keyword in all_keywords:
            if keyword.lower() in text:
                return True, keyword
        return False, None

# Create global bot instance
bot_instance = AntiSpamBot()

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Check if user is group admin or in private chat"""
    try:
        chat_id = update.effective_chat.id
        
        # Allow all operations in private chat
        if update.effective_chat.type == 'private':
            return True
            
        cache_key = f"{chat_id}_{user_id}"
        current_time = asyncio.get_event_loop().time()
        
        # Check cache for group chats
        if cache_key in admin_cache:
            cache_time, is_admin_cached = admin_cache[cache_key]
            if current_time - cache_time < CACHE_DURATION:
                return is_admin_cached
        
        # Get user permissions in group
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin_result = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        
        # Update cache
        admin_cache[cache_key] = (current_time, is_admin_result)
        
        return is_admin_result
        
    except Exception as e:
        logger.error(f"Failed to check admin permissions: {e}")
        return False

def admin_required(func):
    """Admin permission decorator"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await is_admin(update, context, update.effective_user.id):
            return await func(update, context)
        else:
            await update.message.reply_text("❌ This command is only for group admins")
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    welcome_text = """🤖 Anti-spam bot started!

📝 Admin commands:
• /add <keyword> - Add keyword
• /delete <keyword> - Delete keyword  
• /list - View keyword list
• /stats - View statistics

⚡ Functions:
• Auto detect and delete spam/ads
• Support gambling and adult content filtering

💡 Usage:
Please ensure bot has delete message admin permissions"""
    
    await update.message.reply_text(welcome_text)

@admin_required
async def add_keyword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add keyword command"""
    if not context.args:
        await update.message.reply_text("❌ Please provide keyword to add\nUsage: /add <keyword>")
        return
    
    keyword = ' '.join(context.args)
    if bot_instance.add_keyword(keyword):
        await update.message.reply_text(f"✅ Added keyword: {keyword}")
    else:
        await update.message.reply_text(f"❌ Keyword already exists: {keyword}")

@admin_required  
async def delete_keyword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete keyword command"""
    if not context.args:
        await update.message.reply_text("❌ Please provide keyword to delete\nUsage: /delete <keyword>")
        return
    
    keyword = ' '.join(context.args)
    if bot_instance.remove_keyword(keyword):
        await update.message.reply_text(f"✅ Deleted keyword: {keyword}")
    else:
        await update.message.reply_text(f"❌ Keyword not found: {keyword}")

@admin_required
async def list_keywords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all keywords command"""
    keywords_data = bot_instance.keywords_data
    
    if not any(keywords_data.values()):
        await update.message.reply_text("📝 Keyword list is empty")
        return
    
    message_parts = ["📝 Current keyword list:\n"]
    
    for category, keywords in keywords_data.items():
        if keywords:
            category_name = {
                "gambling": "🎰 Gambling",
                "adult": "🔞 Adult", 
                "custom": "⚙️ Custom"
            }.get(category, f"📂 {category}")
            
            message_parts.append(f"\n{category_name}:")
            for i, keyword in enumerate(keywords[:10], 1):
                message_parts.append(f"{i}. {keyword}")
            
            if len(keywords) > 10:
                message_parts.append(f"... and {len(keywords) - 10} more keywords")
    
    response = '\n'.join(message_parts)
    if len(response) > 4000:
        response = response[:4000] + "\n\n... (message too long, truncated)"
    
    await update.message.reply_text(response)

@admin_required
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistics command"""
    keywords_data = bot_instance.keywords_data
    total_keywords = sum(len(keywords) for keywords in keywords_data.values())
    
    stats_text = f"""📊 Bot Statistics

🔢 Total keywords: {total_keywords}
• 🎰 Gambling: {len(keywords_data.get('gambling', []))}
• 🔞 Adult: {len(keywords_data.get('adult', []))}  
• ⚙️ Custom: {len(keywords_data.get('custom', []))}

📅 Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🟢 Status: Running normally"""
    
    await update.message.reply_text(stats_text)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message handler - check for spam"""
    if not update.message or not update.message.text:
        return
    
    # Ignore group admin messages
    if await is_admin(update, context, update.effective_user.id):
        return
    
    message_text = update.message.text
    is_spam, matched_keyword = bot_instance.check_spam(message_text)
    
    if is_spam:
        try:
            # Delete spam message
            await update.message.delete()
            
            # Send notification
            chat = update.effective_chat
            warning_msg = await chat.send_message(f"🗑️ Deleted spam message (matched: {matched_keyword})")
            
            # Delete warning message after 5 seconds
            await asyncio.sleep(5)
            try:
                await warning_msg.delete()
            except:
                pass
                
            logger.info(f"Deleted spam message: {message_text[:50]}... (matched: {matched_keyword})")
            
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")

async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Health check endpoint"""
    await update.message.reply_text("🟢 Bot running normally")

def main():
    """Main function"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not found")
        return
    
    # Start HTTP server in a separate thread for Render health checks
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Start keep-alive service to prevent Render from sleeping
    start_keep_alive()
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_keyword_command))
    application.add_handler(CommandHandler("delete", delete_keyword_command))
    application.add_handler(CommandHandler("list", list_keywords_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("health", health_check))
    
    # Add message handler
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS,
        message_handler
    ))
    
    logger.info("🤖 Anti-spam bot started successfully!")
    logger.info(f"📝 Current total keywords: {sum(len(keywords) for keywords in bot_instance.keywords_data.values())}")
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
