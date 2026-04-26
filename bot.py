"""
Bot Discord Tout-en-Un - 100% GRATUIT
=======================================
✅ Traduction à la demande
✅ Miroir de salon (traduction automatique)
✅ Réaction 🌐 pour traduire
✅ Financial Juice RSS → Français en temps réel

Variables d'environnement :
  DISCORD_TOKEN   - Token du bot Discord (obligatoire)
  FJ_CHANNEL_ID   - ID du salon où poster les news FJ (obligatoire pour le RSS)
  FJ_INTERVAL     - Intervalle RSS en secondes (optionnel, défaut = 60)
"""

import discord
from discord.ext import commands, tasks
from deep_translator import GoogleTranslator
from deep_translator.exceptions import LanguageNotSupportedException, TranslationNotFound
from langdetect import detect, DetectorFactory
import feedparser
from typing import Optional
from datetime import datetime, timezone
import os

DetectorFactory.seed = 0

# ─── CONFIG ──────────────────────────────────────────────────────────────────

DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN", "VOTRE_TOKEN_DISCORD_ICI")
DEFAULT_LANG   = "fr"
FJ_CHANNEL_ID  = int(os.getenv("FJ_CHANNEL_ID", "0"))
FJ_RSS_URL     = os.getenv("FJ_RSS_URL", "https://www.financialjuice.com/feed.aspx")
FJ_INTERVAL    = int(os.getenv("FJ_INTERVAL", "60"))

LANGUAGES = {
    "af": "afrikaans", "sq": "albanais", "am": "amharique", "ar": "arabe",
    "hy": "arménien", "az": "azerbaïdjanais", "eu": "basque", "be": "biélorusse",
    "bn": "bengali", "bs": "bosnien", "bg": "bulgare", "ca": "catalan",
    "ceb": "cebuano", "zh-cn": "chinois simplifié", "zh-tw": "chinois traditionnel",
    "co": "corse", "hr": "croate", "cs": "tchèque", "da": "danois",
    "nl": "néerlandais", "en": "anglais", "eo": "espéranto", "et": "estonien",
    "fi": "finnois", "fr": "français", "fy": "frison", "gl": "galicien",
    "ka": "géorgien", "de": "allemand", "el": "grec", "gu": "gujarati",
    "ht": "haïtien", "ha": "haoussa", "haw": "hawaïen", "he": "hébreu",
    "hi": "hindi", "hmn": "hmong", "hu": "hongrois", "is": "islandais",
    "ig": "igbo", "id": "indonésien", "ga": "irlandais", "it": "italien",
    "ja": "japonais", "jw": "javanais", "kn": "kannada", "kk": "kazakh",
    "km": "khmer", "ko": "coréen", "ku": "kurde", "ky": "kirghiz",
    "lo": "laotien", "la": "latin", "lv": "letton", "lt": "lituanien",
    "lb": "luxembourgeois", "mk": "macédonien", "mg": "malgache", "ms": "malais",
    "ml": "malayalam", "mt": "maltais", "mi": "maori", "mr": "marathi",
    "mn": "mongol", "my": "birman", "ne": "népalais", "no": "norvégien",
    "ny": "nyanja", "or": "oriya", "ps": "pachto", "fa": "persan",
    "pl": "polonais", "pt": "portugais", "pa": "pendjabi", "ro": "roumain",
    "ru": "russe", "sm": "samoan", "gd": "gaélique écossais", "sr": "serbe",
    "st": "sesotho", "sn": "shona", "sd": "sindhi", "si": "cingalais",
    "sk": "slovaque", "sl": "slovène", "so": "somali", "es": "espagnol",
    "su": "soundanais", "sw": "swahili", "sv": "suédois", "tl": "tagalog",
    "tg": "tadjik", "ta": "tamoul", "te": "télougou", "th": "thaï",
    "tr": "turc", "uk": "ukrainien", "ur": "ourdou", "ug": "ouïghour",
    "uz": "ouzbek", "vi": "vietnamien", "cy": "gallois", "xh": "xhosa",
    "yi": "yiddish", "yo": "yoruba", "zu": "zoulou",
}

LANG_NAME_TO_CODE = {v.lower(): k for k, v in LANGUAGES.items()}
LANG_NAME_TO_CODE.update({
    "chinois": "zh-cn", "anglais": "en", "français": "fr", "espagnol": "es",
    "allemand": "de", "italien": "it", "japonais": "ja", "coréen": "ko",
    "russe": "ru", "arabe": "ar",
})

channel_default_lang: dict[int, str] = {}
mirrors: dict[int, dict] = {}
fj_posted_ids: set[str] = set()

# ─── SETUP ───────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def resolve_lang(lang_input: str) -> str:
    s = lang_input.lower().strip()
    if s in LANGUAGES:
        return s
    if s in LANG_NAME_TO_CODE:
        return LANG_NAME_TO_CODE[s]
    for name, code in LANG_NAME_TO_CODE.items():
        if s in name:
            return code
    return s

def lang_display(code: str) -> str:
    return LANGUAGES.get(code.lower(), code).capitalize()

def do_translate(text: str, target: str, source: str = "auto") -> tuple[str, str]:
    translated = GoogleTranslator(source=source, target=target).translate(text)
    try:
        detected = detect(text)
    except Exception:
        detected = "?"
    return translated, detected

def translate_fr(text: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="fr").translate(text) or text
    except Exception:
        return text

def parse_rss_date(entry) -> str:
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        pass
    return ""


# ─── TÂCHE RSS ────────────────────────────────────────────────────────────────

@tasks.loop(seconds=FJ_INTERVAL)
async def check_fj_rss():
    if FJ_CHANNEL_ID == 0:
        return
    channel = bot.get_channel(FJ_CHANNEL_ID)
    if not channel:
        return
    try:
        feed = feedparser.parse(FJ_RSS_URL)
    except Exception as e:
        print(f"❌ Erreur RSS : {e}")
        return

    for entry in reversed(feed.entries):
        uid = getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")
        if not uid or uid in fj_posted_ids:
            continue
        fj_posted_ids.add(uid)
        raw = getattr(entry, "title", "").strip()
        if not raw:
            continue
        translated = translate_fr(raw)
        link = getattr(entry, "link", "")
        pub_date = parse_rss_date(entry)
        embed = discord.Embed(description=f"**{translated}**", color=0x2ECC71, url=link or None)
        embed.set_author(name="📰 Financial Juice")
        if pub_date:
            embed.set_footer(text=pub_date)
        try:
            await channel.send(embed=embed)
            print(f"📰 FJ : {translated[:80]}")
        except Exception as e:
            print(f"❌ Erreur envoi RSS : {e}")


@check_fj_rss.before_loop
async def before_fj_rss():
    await bot.wait_until_ready()
    print("🔄 Initialisation RSS Financial Juice...")
    try:
        feed = feedparser.parse(FJ_RSS_URL)
        for entry in feed.entries:
            uid = getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")
            if uid:
                fj_posted_ids.add(uid)
        print(f"✅ {len(fj_posted_ids)} entrées RSS existantes ignorées.")
    except Exception as e:
        print(f"⚠️  Erreur init RSS : {e}")


# ─── EVENTS ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ {bot.user} connecté !")
    print(f"   Serveurs  : {len(bot.guilds)}")
    print(f"   Salon RSS : {FJ_CHANNEL_ID or 'non configuré'}")
    check_fj_rss.start()
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="Financial Juice 📰 | !aide")
    )


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)
    if message.author == bot.user:
        return
    if not message.content or message.content.startswith("!"):
        return
    if message.channel.id not in mirrors:
        return
    config = mirrors[message.channel.id]
    target_channel = bot.get_channel(config["target_id"])
    if not target_channel:
        return
    try:
        translated, detected = do_translate(message.content, config["lang"])
        if detected == config["lang"]:
            return
        embed = discord.Embed(description=translated, color=0x5865F2, timestamp=message.created_at)
        embed.set_footer(text=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="", value=f"[↗ Message original]({message.jump_url})", inline=False)
        await target_channel.send(embed=embed)
    except Exception:
        pass


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) != "🌐":
        return
    if payload.user_id == bot.user.id:
        return
    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return
    if not message.content or message.author == bot.user:
        return
    target = channel_default_lang.get(channel.id, DEFAULT_LANG)
    user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
    member = channel.guild.get_member(payload.user_id) or user
    async with channel.typing():
        try:
            translated, detected = do_translate(message.content, target)
            await message.reply(
                f"{translated}\n-# 🌐 Traduit du {lang_display(detected)} → {lang_display(target)}",
                mention_author=False,
            )
        except Exception as e:
            await channel.send(f"❌ Erreur : {e}", delete_after=10)


# ─── COMMANDES TRADUCTION ─────────────────────────────────────────────────────

@bot.command(name="translate", aliases=["tl", "tr"])
async def translate_cmd(ctx: commands.Context, lang: Optional[str] = None, *, text: Optional[str] = None):
    if not lang or not text:
        await ctx.send("❌ Usage : `!translate <langue> <texte>`", delete_after=15)
        return
    target = resolve_lang(lang)
    async with ctx.typing():
        try:
            translated, detected = do_translate(text, target)
            await ctx.reply(
                f"{translated}\n-# 🌐 Traduit du {lang_display(detected)} → {lang_display(target)}",
                mention_author=False,
            )
        except Exception as e:
            await ctx.send(f"❌ Erreur : `{e}`", delete_after=10)


@bot.command(name="detect")
async def detect_cmd(ctx: commands.Context, *, text: Optional[str] = None):
    if not text:
        await ctx.send("❌ Usage : `!detect <texte>`", delete_after=10)
        return
    try:
        code = detect(text)
        embed = discord.Embed(title="🔍 Détection de langue", color=0x57F287)
        embed.add_field(name="Texte", value=f"```{text[:500]}```", inline=False)
        embed.add_field(name="Langue détectée", value=f"**{lang_display(code)}** (`{code}`)", inline=True)
        await ctx.reply(embed=embed, mention_author=False)
    except Exception as e:
        await ctx.send(f"❌ Erreur : `{e}`", delete_after=10)


@bot.command(name="setlang")
async def setlang_cmd(ctx: commands.Context, *, lang: Optional[str] = None):
    if not lang:
        current = channel_default_lang.get(ctx.channel.id, DEFAULT_LANG)
        await ctx.send(f"🌐 Langue actuelle : **{lang_display(current)}** — Usage : `!setlang <langue>`")
        return
    code = resolve_lang(lang)
    channel_default_lang[ctx.channel.id] = code
    await ctx.send(f"✅ Langue par défaut : **{lang_display(code)}** (`{code}`).")


@bot.command(name="languages", aliases=["langs", "langues"])
async def languages_cmd(ctx: commands.Context):
    popular = ["fr", "en", "es", "de", "it", "pt", "ru", "zh-cn", "ja", "ko", "ar", "nl", "pl", "tr", "sv", "uk", "hi", "vi", "th", "el"]
    embed = discord.Embed(title="🌍 Langues supportées", color=0xFEE75C,
        description=f"**{len(LANGUAGES)} langues** disponibles.")
    embed.add_field(name="Populaires", value=" ".join(f"`{c}`" for c in popular), inline=False)
    await ctx.send(embed=embed)


# ─── COMMANDES MIROIR ─────────────────────────────────────────────────────────

@bot.command(name="mirror")
@commands.has_permissions(manage_channels=True)
async def mirror_cmd(ctx: commands.Context, source: discord.TextChannel, target: discord.TextChannel, lang: str = "fr"):
    code = resolve_lang(lang)
    mirrors[source.id] = {"target_id": target.id, "lang": code}
    await ctx.send(f"✅ Miroir activé : {source.mention} → {target.mention} en **{lang_display(code)}**.")


@bot.command(name="unmirror")
@commands.has_permissions(manage_channels=True)
async def unmirror_cmd(ctx: commands.Context, source: discord.TextChannel):
    if source.id in mirrors:
        del mirrors[source.id]
        await ctx.send(f"✅ Miroir désactivé pour {source.mention}.")
    else:
        await ctx.send(f"❌ Aucun miroir actif sur {source.mention}.")


@bot.command(name="mirrors")
async def mirrors_cmd(ctx: commands.Context):
    if not mirrors:
        await ctx.send("Aucun miroir actif. Utilise `!mirror <#source> <#cible> <langue>`.")
        return
    embed = discord.Embed(title="🪞 Miroirs actifs", color=0x5865F2)
    for sid, cfg in mirrors.items():
        sc = bot.get_channel(sid)
        tc = bot.get_channel(cfg["target_id"])
        embed.add_field(
            name=f"{sc.mention if sc else sid} → {tc.mention if tc else cfg['target_id']}",
            value=f"Langue : **{lang_display(cfg['lang'])}**", inline=False)
    await ctx.send(embed=embed)


# ─── COMMANDES RSS FINANCIAL JUICE ────────────────────────────────────────────

@bot.command(name="fjtest")
async def fjtest_cmd(ctx: commands.Context):
    await ctx.send(f"🔄 Lecture du flux : `{FJ_RSS_URL}`")
    try:
        feed = feedparser.parse(FJ_RSS_URL)
        await ctx.send(f"📡 Statut HTTP : `{getattr(feed, 'status', '?')}` — Entrées : `{len(feed.entries)}`")
        if feed.bozo:
            await ctx.send(f"⚠️ Erreur RSS : `{feed.bozo_exception}`")
        if not feed.entries:
            await ctx.send("❌ Aucune entrée trouvée.")
            return
        entry = feed.entries[0]
        raw = getattr(entry, "title", "").strip()
        await ctx.send(f"📝 Titre brut : `{raw}`")
        translated = translate_fr(raw)
        await ctx.send(f"🌐 Traduit : `{translated}`")
        link = getattr(entry, "link", "")
        pub_date = parse_rss_date(entry)
        embed = discord.Embed(description=f"**{translated}**", color=0x2ECC71, url=link or None)
        embed.set_author(name="📰 Financial Juice")
        embed.set_footer(text=f"{pub_date} • Test")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Erreur : `{e}`")


@bot.command(name="fjstatus")
async def fjstatus_cmd(ctx: commands.Context):
    embed = discord.Embed(title="📊 Statut Financial Juice RSS", color=0x3498DB)
    embed.add_field(name="Flux RSS", value=f"`{FJ_RSS_URL}`", inline=False)
    embed.add_field(name="Salon cible", value=f"<#{FJ_CHANNEL_ID}>" if FJ_CHANNEL_ID else "❌ Non configuré", inline=True)
    embed.add_field(name="Intervalle", value=f"`{FJ_INTERVAL}s`", inline=True)
    embed.add_field(name="News postées", value=f"`{len(fj_posted_ids)}`", inline=True)
    embed.add_field(name="Boucle active", value="✅ Oui" if check_fj_rss.is_running() else "❌ Non", inline=True)
    await ctx.send(embed=embed)


@bot.command(name="fjsetchannel")
@commands.has_permissions(manage_channels=True)
async def fjsetchannel_cmd(ctx: commands.Context, channel: discord.TextChannel):
    global FJ_CHANNEL_ID
    FJ_CHANNEL_ID = channel.id
    await ctx.send(
        f"✅ News Financial Juice → {channel.mention}\n"
        f"⚠️ Pour rendre permanent, ajoute `FJ_CHANNEL_ID={channel.id}` dans tes variables Railway."
    )


# ─── AIDE ────────────────────────────────────────────────────────────────────

@bot.command(name="aide", aliases=["help_translate", "thelp"])
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(title="🤖 Bot Discord — Aide", color=0x5865F2,
        description="Traduction + Miroir + Financial Juice RSS • 100% gratuit")
    embed.add_field(name="🌐 Traduction", value=(
        "`!translate <langue> <texte>`\n`!tl <langue> <texte>`\n"
        "`!detect <texte>`\n`!setlang <langue>`\n`!languages`\nRéaction **🌐** sur un message"
    ), inline=False)
    embed.add_field(name="🪞 Miroir", value=(
        "`!mirror <#source> <#cible> <langue>`\n`!unmirror <#source>`\n`!mirrors`"
    ), inline=False)
    embed.add_field(name="📰 Financial Juice", value=(
        "`!fjtest` — Teste le flux RSS\n`!fjstatus` — Statut\n`!fjsetchannel <#salon>` — Définit le salon"
    ), inline=False)
    await ctx.send(embed=embed)


# ─── LANCEMENT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if DISCORD_TOKEN == "VOTRE_TOKEN_DISCORD_ICI":
        print("⚠️  Configure DISCORD_TOKEN dans tes variables Railway !")
    else:
        print("🚀 Démarrage du bot...")
        bot.run(DISCORD_TOKEN)
