import os
import re
import json
import asyncio
import subprocess
import shutil
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = "8131660883:AAHmvExkEHW4uWaxL_407yQpugatc8TQeZA"
SESSION_FILE = "session-tremxvr_"
COOKIES_FILE = "cookies.txt"

user_states = {}

def is_reel_link(url: str) -> bool:
    return bool(re.search(r"instagram\.com/(reel|reels)/[^\s/?#]+", url, re.IGNORECASE))

def is_story_link(url: str) -> bool:
    return bool(re.search(r"instagram\.com/stories/[^/]+/\d+", url, re.IGNORECASE))

def is_profile_link(url: str) -> str | None:
    match = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", url)
    return match.group(1) if match else None

def extrair_username(url: str) -> str | None:
    return is_profile_link(url)

def baixar_foto_perfil(username: str) -> str:
    temp_dir = "perfil"
    cmd = [
        "instaloader",
        "--sessionfile", SESSION_FILE,
        "--no-posts",
        "--no-metadata-json",
        "--no-compress-json",
        "--dirname-pattern", temp_dir,
        username,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception("❌ Não foi possível acessar o perfil com instaloader.")

    # Procurar a foto de perfil que termina com _profile_pic.jpg
    for raiz, _, arquivos in os.walk(temp_dir):
        for arquivo in arquivos:
            if arquivo.endswith("_profile_pic.jpg"):
                origem = os.path.join(raiz, arquivo)
                destino = "foto_temp.jpg"
                with open(origem, "rb") as src, open(destino, "wb") as dst:
                    dst.write(src.read())
                return destino

    raise FileNotFoundError("❌ Foto de perfil não encontrada.")

def get_video_info(url: str) -> dict:
    cmd = ['yt-dlp', '--cookies', COOKIES_FILE, '--dump-json', url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception("Falha ao obter informações do vídeo.")
    return json.loads(result.stdout)

async def download_video(url: str, filename: str) -> str:
    cmd = [
        'yt-dlp',
        '-f', 'mp4[height<=720]+bestaudio/best',
        '--cookies', COOKIES_FILE,
        '-o', filename,
        url,
    ]
    await asyncio.to_thread(lambda: subprocess.run(cmd, capture_output=True))
    if not os.path.exists(filename):
        raise Exception("❌ Erro: vídeo não baixado.")
    return filename

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>👋 Olá! Use o comando /baixar para escolher o que deseja baixar do Instagram.</b>",
        parse_mode="HTML"
    )

async def baixar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📸 Baixar foto do perfil", callback_data="foto")],
        [InlineKeyboardButton("🎞️ Baixar Stories", callback_data="story")],
        [InlineKeyboardButton("🎬 Baixar Reels", callback_data="reel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "<b>Escolha o que deseja baixar:</b>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_states[user_id] = query.data

    texto = {
        "foto": "🔗 Envie o link do perfil do Instagram:",
        "story": "🔗 Envie o link do story:",
        "reel": "🔗 Envie o link do Reels:"
    }.get(query.data, "❓ Opção desconhecida.")

    await query.edit_message_text(texto)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    url = update.message.text.strip()

    if user_id not in user_states:
        await update.message.reply_text("⚠️ Use /baixar antes de enviar um link.")
        return

    escolha = user_states[user_id]
    msg = await update.message.reply_text("<b>⏳ Processando, aguarde...</b>", parse_mode="HTML")

    try:
        if escolha == "foto":
            username = extrair_username(url)
            if not username:
                raise Exception("❌ Link de perfil inválido.")
            foto_path = baixar_foto_perfil(username)
            if os.path.exists(foto_path):
                with open(foto_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo,
                        caption=f"<b>✅ Foto de perfil baixada com sucesso!</b>",
                        parse_mode="HTML",
                    )
                os.remove(foto_path)
            else:
                raise Exception("❌ Foto não encontrada após o download.")

            # Apagar pasta temporária 'perfil'
            if os.path.isdir("perfil"):
                shutil.rmtree("perfil", ignore_errors=True)

        elif escolha in ("reel", "story"):
            tipo = "Reels" if escolha == "reel" else "Stories"
            filename = "reel_instagram.mp4" if escolha == "reel" else "story_instagram.mp4"
            info = await asyncio.to_thread(get_video_info, url)
            video_path = await download_video(url, filename)
            with open(video_path, "rb") as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    caption=f"<b>✅ Vídeo de {tipo} baixado com sucesso! 🎥</b>",
                    parse_mode="HTML",
                )
            os.remove(video_path)

        else:
            await update.message.reply_text("❌ Tipo de operação desconhecido.")

    except Exception as e:
        await msg.edit_text(f"<b>❌ Erro:</b>\n<code>{str(e)}</code>", parse_mode="HTML")
    else:
        await msg.delete()
        user_states.pop(user_id, None)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("baixar", baixar))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("\033[1;32m\033[4m✅ BOT INICIADO MANUALMENTE\033[0m")
    print("\033[1;36mDesenvolvido por: barretoxs\033[0m\n")

    app.run_polling()

    print("\033[1;31m\033[4m❌ BOT ENCERRADO MANUALMENTE\033[0m")
    print("\033[1;36mDesenvolvido por: barretoxs\033[0m")

if __name__ == "__main__":
    main()
