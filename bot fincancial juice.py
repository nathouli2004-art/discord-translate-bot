"""
Bot Discord — Financial Juice RSS → Français en temps réel
============================================================
Surveille le flux RSS de Financial Juice toutes les 60 secondes
et poste les nouvelles actualités traduites en français dans un salon Discord.

Configuration (variables d'environnement) :
  DISCORD_TOKEN      - Token du bot Discord (obligatoire)
  FJ_CHANNEL_ID      - ID du salon Discord où poster les news (obligatoire)
  FJ_RSS_URL         - URL du flux RSS (optionnel, défaut = financialjuice.com/feed.aspx)
  FJ_INTERVAL        - Intervalle de vérification en secondes (optionnel, défaut = 60)
"""

import discord
from discord.ext import commands, tasks
from deep_translator import GoogleTranslator
import feedparser
import os
from datetime import datetime, timezone

# ─── CONFIG ──────────────────────────────────────────────────────────────────

DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN", "VOTRE_TOKEN_DISCORD_ICI")
FJ_CHANNEL_ID  = int(os.getenv("FJ_CHANNEL_ID", "0"))   # ID du salon cible
RSS_URL        = os.getenv("FJ_RSS_URL", "https://www.financialjuice.com/feed.aspx")
CHECK_INTERVAL = int(os.getenv("FJ_INTERVAL", "60"))     # secondes

# IDs des entrées déjà postées (évite les doublons)
posted_ids: set[str] = set()

# ─── SETUP ───────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def translate_fr(text: str) -> str:
    """Traduit en français via Google Translate (gratuit, sans clé)."""
    try:
        return GoogleTranslator(source="auto", target="fr").translate(text) or text
    except Exception:
        return text  # En cas d'erreur, retourne le texte original


def build_embed(title: str, link: str, pub_date: str) -> discord.Embed:
    """Construit l'embed Discord pour une news."""
    embed = discord.Embed(
        description=f"**{title}**",
        color=0x2ECC71,
        url=link if link else None,
    )
    embed.set_author(
        name="📰 Financial Juice",
        icon_url="https://www.financialjuice.com/assets/images/FjLogo.svg",
    )
    if pub_date:
        embed.set_footer(text=pub_date)
    return embed


def parse_date(entry) -> str:
    """Extrait et formate la date d'une entrée RSS."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        pass
    return ""


# ─── TÂCHE DE FOND ───────────────────────────────────────────────────────────

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_rss():
    """Vérifie le RSS Financial Juice et poste les nouvelles entrées."""
    channel = bot.get_channel(FJ_CHANNEL_ID)
    if not channel:
        print(f"⚠️  Salon introuvable (ID: {FJ_CHANNEL_ID})")
        return

    try:
        feed = feedparser.parse(RSS_URL)
    except Exception as e:
        print(f"❌ Erreur RSS : {e}")
        return

    if feed.bozo and not feed.entries:
        print(f"⚠️  Flux RSS invalide ou inaccessible : {RSS_URL}")
        return

    # Trier du plus ancien au plus récent pour poster dans l'ordre chronologique
    entries = list(reversed(feed.entries))

    for entry in entries:
        # Identifiant unique de l'entrée
        uid = getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")
        if not uid or uid in posted_ids:
            continue

        posted_ids.add(uid)

        # Récupérer le titre
        raw_title = getattr(entry, "title", "").strip()
        if not raw_title:
            continue

        # Traduire en français
        translated = translate_fr(raw_title)

        # Lien et date
        link     = getattr(entry, "link", "")
        pub_date = parse_date(entry)

        # Construire et envoyer l'embed
        embed = build_embed(translated, link, pub_date)
        try:
            await channel.send(embed=embed)
            print(f"✅ Posté : {translated[:80]}")
        except discord.Forbidden:
            print(f"❌ Permission refusée dans le salon {FJ_CHANNEL_ID}")
        except Exception as e:
            print(f"❌ Erreur envoi : {e}")


@check_rss.before_loop
async def before_check():
    """Attend que le bot soit prêt avant de démarrer la boucle."""
    await bot.wait_until_ready()

    # Pré-remplir les IDs déjà existants pour ne pas repostter
    # les anciennes news au démarrage
    print("🔄 Initialisation — lecture du flux RSS...")
    try:
        feed = feedparser.parse(RSS_URL)
        for entry in feed.entries:
            uid = getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")
            if uid:
                posted_ids.add(uid)
        print(f"✅ {len(posted_ids)} entrées existantes ignorées.")
    except Exception as e:
        print(f"⚠️  Impossible de lire le flux au démarrage : {e}")


# ─── EVENTS ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ {bot.user} connecté !")
    print(f"   Salon cible : {FJ_CHANNEL_ID}")
    print(f"   Flux RSS    : {RSS_URL}")
    print(f"   Intervalle  : {CHECK_INTERVAL}s")
    check_rss.start()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Financial Juice 📰"
        )
    )


# ─── COMMANDES ADMIN ─────────────────────────────────────────────────────────

@bot.command(name="fjstatus")
async def status_cmd(ctx: commands.Context):
    """!fjstatus — Affiche le statut du bot RSS."""
    embed = discord.Embed(title="📊 Statut Financial Juice Bot", color=0x3498DB)
    embed.add_field(name="Flux RSS", value=f"`{RSS_URL}`", inline=False)
    embed.add_field(name="Intervalle", value=f"`{CHECK_INTERVAL}s`", inline=True)
    embed.add_field(name="News postées", value=f"`{len(posted_ids)}`", inline=True)
    embed.add_field(name="Boucle active", value="✅ Oui" if check_rss.is_running() else "❌ Non", inline=True)
    await ctx.send(embed=embed)


@bot.command(name="fjtest")
async def test_cmd(ctx: commands.Context):
    """!fjtest — Poste manuellement la dernière news du flux."""
    await ctx.send(f"🔄 Tentative de lecture du flux : `{RSS_URL}`")
    try:
        feed = feedparser.parse(RSS_URL)
        await ctx.send(f"📡 Statut flux : `{feed.status if hasattr(feed, 'status') else 'inconnu'}` — Entrées trouvées : `{len(feed.entries)}`")
        if feed.bozo:
            await ctx.send(f"⚠️ Erreur de parsing RSS : `{feed.bozo_exception}`")
        if not feed.entries:
            await ctx.send("❌ Aucune entrée dans le flux RSS. Le flux est peut-être vide ou l'URL est incorrecte.")
            return
        entry = feed.entries[0]
        raw   = getattr(entry, "title", "Pas de titre").strip()
        await ctx.send(f"📝 Titre brut : `{raw}`")
        translated = translate_fr(raw)
        await ctx.send(f"🌐 Traduit : `{translated}`")
        link  = getattr(entry, "link", "")
        date  = parse_date(entry)
        embed = build_embed(translated, link, date)
        embed.set_footer(text=f"{date} • Test manuel")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Erreur : `{e}`")


@bot.command(name="fjurl")
async def url_cmd(ctx: commands.Context, *, url: str = None):
    """!fjurl <url> — Teste un autre URL de flux RSS."""
    global RSS_URL
    if url:
        RSS_URL = url.strip()
        await ctx.send(f"✅ URL mise à jour : `{RSS_URL}`\nRelance `!fjtest` pour tester.")
    else:
        await ctx.send(f"URL actuelle : `{RSS_URL}`")


# ─── LANCEMENT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if DISCORD_TOKEN == "VOTRE_TOKEN_DISCORD_ICI" or FJ_CHANNEL_ID == 0:
        print("⚠️  Configure tes variables d'environnement !")
        print()
        print("   Variables requises :")
        print("   DISCORD_TOKEN  = ton token Discord")
        print("   FJ_CHANNEL_ID  = l'ID du salon Discord où poster les news")
        print()
        print("   Comment trouver l'ID d'un salon Discord :")
        print("   Paramètres Discord → Apparence → Mode développeur ON")
        print("   Clic droit sur le salon → Copier l'identifiant")
        print()
        print("   Exemple :")
        print("   export DISCORD_TOKEN='ton_token'")
        print("   export FJ_CHANNEL_ID='123456789012345678'")
    else:
        print("🚀 Démarrage du bot Financial Juice RSS...")
        bot.run(DISCORD_TOKEN)
