"""
Bot de Traduction Discord - 100% GRATUIT
=========================================
Utilise deep-translator (Google Translate) — aucune clé API requise.

Commandes :
  !translate <langue> <texte>   - Traduit un texte
  !tl <langue> <texte>          - Alias court
  !detect <texte>               - Détecte la langue
  !languages                    - Liste des langues supportées
  !setlang <langue>             - Langue par défaut du channel
  !mirror <#salon-source> <#salon-cible> <langue>  - Active le miroir automatique
  !unmirror <#salon-source>     - Désactive le miroir
  !mirrors                      - Liste les miroirs actifs
  !help_translate               - Aide

Réaction automatique :
  Réagis avec 🌐 sur n'importe quel message → traduction automatique.
"""

import discord
from discord.ext import commands
from deep_translator import GoogleTranslator
from deep_translator.exceptions import LanguageNotSupportedException, TranslationNotFound
import langdetect
from langdetect import detect, DetectorFactory
from typing import Optional
import os

# Rendre langdetect déterministe
DetectorFactory.seed = 0

# ─── CONFIG ──────────────────────────────────────────────────────────────────

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "VOTRE_TOKEN_DISCORD_ICI")
DEFAULT_LANG = "fr"   # Langue cible par défaut pour la réaction 🌐

# Langues disponibles (deep-translator supporte tout ce que Google Translate supporte)
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

# Noms français → code ISO
LANG_NAME_TO_CODE = {v.lower(): k for k, v in LANGUAGES.items()}
# Ajouter quelques alias communs
LANG_NAME_TO_CODE.update({
    "chinois": "zh-cn", "portugais brésilien": "pt",
    "anglais": "en", "français": "fr", "espagnol": "es",
    "allemand": "de", "italien": "it", "japonais": "ja",
    "coréen": "ko", "russe": "ru", "arabe": "ar",
    "chinois simplifié": "zh-cn", "chinois traditionnel": "zh-tw",
})

# Langue par défaut par channel (en mémoire)
channel_default_lang: dict[int, str] = {}

# Miroirs : {id_salon_source: {"target_id": int, "lang": "fr"}}
mirrors: dict[int, dict] = {}

# ─── SETUP ───────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def resolve_lang(lang_input: str) -> str:
    """
    Résout n'importe quel input en code ISO valide pour deep-translator.
    Accepte : 'fr', 'french', 'français', 'FR', etc.
    """
    s = lang_input.lower().strip()

    # Code direct
    if s in LANGUAGES:
        return s

    # Nom en français ou en anglais
    if s in LANG_NAME_TO_CODE:
        return LANG_NAME_TO_CODE[s]

    # Recherche partielle (ex: "portug" → "portugais")
    for name, code in LANG_NAME_TO_CODE.items():
        if s in name:
            return code

    return s  # On laisse passer, deep-translator lèvera une erreur claire


def lang_display(code: str) -> str:
    """Retourne le nom affiché d'un code langue."""
    return LANGUAGES.get(code.lower(), code).capitalize()


def do_translate(text: str, target: str, source: str = "auto") -> tuple[str, str]:
    """
    Traduit avec deep-translator (Google Translate, gratuit).
    Retourne (texte_traduit, code_langue_source_détecté).
    """
    translator = GoogleTranslator(source=source, target=target)
    translated = translator.translate(text)

    # Détection de la langue source
    try:
        detected = detect(text)
    except Exception:
        detected = "?"

    return translated, detected


def build_embed(
    original: str,
    translated: str,
    detected: str,
    target: str,
    author: discord.Member | discord.User,
) -> discord.Embed:
    embed = discord.Embed(color=0x5865F2)
    embed.set_author(
        name=f"Traduction demandée par {author.display_name}",
        icon_url=author.display_avatar.url,
    )
    embed.add_field(
        name=f"🔤 Original ({lang_display(detected)})",
        value=f"```{original[:1000]}```",
        inline=False,
    )
    embed.add_field(
        name=f"🌐 Traduction → {lang_display(target)}",
        value=f"```{translated[:1000]}```",
        inline=False,
    )
    embed.set_footer(text="Propulsé par Google Translate via deep-translator • 100% gratuit")
    return embed


# ─── EVENTS ──────────────────────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    """Miroir automatique : retraduit les messages du salon source vers le salon cible."""
    # Toujours traiter les commandes
    await bot.process_commands(message)

    # Ignorer les messages du bot lui-même
    if message.author == bot.user:
        return

    # Ignorer les messages sans texte
    if not message.content or message.content.startswith("!"):
        return

    # Vérifier si ce salon est un salon source de miroir
    if message.channel.id not in mirrors:
        return

    config = mirrors[message.channel.id]
    target_channel = bot.get_channel(config["target_id"])
    if not target_channel:
        return

    try:
        translated, detected = do_translate(message.content, config["lang"])

        # Ne pas retraduire si c'est déjà dans la bonne langue
        if detected == config["lang"]:
            return

        await target_channel.send(
            f"{translated}\n"
            f"-# 🔗 [Message original]({message.jump_url}) • {message.author.display_name}"
        )
    except Exception:
        pass  # On ignore silencieusement pour ne pas spammer en cas d'erreur


@bot.command(name="mirror")
@commands.has_permissions(manage_channels=True)
async def mirror_cmd(ctx: commands.Context, source: discord.TextChannel, target: discord.TextChannel, lang: str = "fr"):
    """!mirror <#salon-source> <#salon-cible> <langue> — Active le miroir automatique."""
    lang_code = resolve_lang(lang)
    mirrors[source.id] = {"target_id": target.id, "lang": lang_code}
    await ctx.send(
        f"✅ Miroir activé !\n"
        f"Tous les messages de {source.mention} seront traduits en **{lang_display(lang_code)}** dans {target.mention}."
    )


@bot.command(name="unmirror")
@commands.has_permissions(manage_channels=True)
async def unmirror_cmd(ctx: commands.Context, source: discord.TextChannel):
    """!unmirror <#salon-source> — Désactive le miroir."""
    if source.id in mirrors:
        del mirrors[source.id]
        await ctx.send(f"✅ Miroir désactivé pour {source.mention}.")
    else:
        await ctx.send(f"❌ Aucun miroir actif sur {source.mention}.")


@bot.command(name="mirrors")
async def mirrors_cmd(ctx: commands.Context):
    """!mirrors — Liste les miroirs actifs."""
    if not mirrors:
        await ctx.send("Aucun miroir actif. Utilise `!mirror <#source> <#cible> <langue>` pour en créer un.")
        return

    embed = discord.Embed(title="🪞 Miroirs actifs", color=0x5865F2)
    for source_id, config in mirrors.items():
        source_ch = bot.get_channel(source_id)
        target_ch = bot.get_channel(config["target_id"])
        source_name = source_ch.mention if source_ch else f"<#{source_id}>"
        target_name = target_ch.mention if target_ch else f"<#{config['target_id']}>"
        embed.add_field(
            name=f"{source_name} → {target_name}",
            value=f"Langue cible : **{lang_display(config['lang'])}**",
            inline=False,
        )
    await ctx.send(embed=embed)



    print(f"✅  {bot.user} est connecté !")
    print(f"   Serveurs : {len(bot.guilds)}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="!translate | réaction 🌐"
        )
    )


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Traduction automatique quand on réagit avec 🌐."""
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

    if not message.content:
        await channel.send("❌ Ce message ne contient pas de texte.", delete_after=8)
        return

    # Ignorer si c'est le bot lui-même
    if message.author == bot.user:
        return

    target = channel_default_lang.get(channel.id, DEFAULT_LANG)
    user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
    member = channel.guild.get_member(payload.user_id) or user

    async with channel.typing():
        try:
            translated, detected = do_translate(message.content, target)
            embed = build_embed(message.content, translated, detected, target, member)
            await message.reply(embed=embed, mention_author=False)
        except LanguageNotSupportedException:
            await channel.send(f"❌ Langue non supportée : `{target}`", delete_after=10)
        except Exception as e:
            await channel.send(f"❌ Erreur de traduction : {e}", delete_after=10)


# ─── COMMANDES ───────────────────────────────────────────────────────────────

@bot.command(name="translate", aliases=["tl", "tr"])
async def translate_cmd(ctx: commands.Context, lang: Optional[str] = None, *, text: Optional[str] = None):
    """!translate <langue> <texte>"""
    if not lang or not text:
        await ctx.send(
            "❌ Usage : `!translate <langue> <texte>`\n"
            "Exemples :\n"
            "• `!translate en Bonjour tout le monde`\n"
            "• `!translate japonais Hello world`\n"
            "• `!tl es Bonne nuit`",
            delete_after=20,
        )
        return

    target = resolve_lang(lang)

    async with ctx.typing():
        try:
            translated, detected = do_translate(text, target)
            embed = build_embed(text, translated, detected, target, ctx.author)
            await ctx.reply(embed=embed, mention_author=False)
        except LanguageNotSupportedException:
            await ctx.send(
                f"❌ Langue inconnue : `{lang}`\n"
                f"Utilise `!languages` pour voir les langues disponibles.",
                delete_after=15,
            )
        except TranslationNotFound:
            await ctx.send("❌ Traduction introuvable pour ce texte.", delete_after=10)
        except Exception as e:
            await ctx.send(f"❌ Erreur : `{e}`", delete_after=10)


@bot.command(name="detect")
async def detect_cmd(ctx: commands.Context, *, text: Optional[str] = None):
    """!detect <texte> — Détecte la langue d'un texte."""
    if not text:
        await ctx.send("❌ Usage : `!detect <texte>`", delete_after=10)
        return

    try:
        code = detect(text)
        name = lang_display(code)
        embed = discord.Embed(title="🔍 Détection de langue", color=0x57F287)
        embed.add_field(name="Texte", value=f"```{text[:500]}```", inline=False)
        embed.add_field(name="Langue détectée", value=f"**{name}** (`{code}`)", inline=True)
        embed.set_footer(text="Propulsé par langdetect • 100% gratuit")
        await ctx.reply(embed=embed, mention_author=False)
    except Exception as e:
        await ctx.send(f"❌ Impossible de détecter la langue : `{e}`", delete_after=10)


@bot.command(name="setlang")
async def setlang_cmd(ctx: commands.Context, *, lang: Optional[str] = None):
    """!setlang <langue> — Langue par défaut du channel pour la réaction 🌐."""
    if not lang:
        current = channel_default_lang.get(ctx.channel.id, DEFAULT_LANG)
        await ctx.send(
            f"🌐 Langue actuelle de ce channel : **{lang_display(current)}** (`{current}`)\n"
            f"Usage : `!setlang <langue>`"
        )
        return

    code = resolve_lang(lang)
    # Valider que la langue existe
    try:
        GoogleTranslator(source="auto", target=code).translate("test")
    except LanguageNotSupportedException:
        await ctx.send(f"❌ Langue inconnue : `{lang}`\nUtilise `!languages` pour la liste.", delete_after=15)
        return
    except Exception:
        pass  # On accepte quand même, l'erreur apparaîtra à la traduction

    channel_default_lang[ctx.channel.id] = code
    await ctx.send(f"✅ Langue par défaut du channel définie sur **{lang_display(code)}** (`{code}`).")


@bot.command(name="languages", aliases=["langs", "langues"])
async def languages_cmd(ctx: commands.Context):
    """!languages — Affiche les langues supportées."""
    # Afficher par groupes pour ne pas dépasser la limite Discord
    popular = ["fr", "en", "es", "de", "it", "pt", "ru", "zh-cn", "ja", "ko", "ar", "nl", "pl", "tr", "sv", "uk", "hi", "vi", "th", "el", "he", "id"]
    popular_text = " ".join(f"`{c}`" for c in popular)

    embed = discord.Embed(
        title="🌍 Langues supportées",
        description=f"Plus de **{len(LANGUAGES)} langues** disponibles (toutes celles de Google Translate).\n\nTu peux utiliser le **code ISO** (`fr`, `en`, `ja`…) ou le **nom** (`français`, `anglais`, `japonais`…).",
        color=0xFEE75C,
    )
    embed.add_field(name="Langues populaires", value=popular_text, inline=False)
    embed.add_field(
        name="Exemples d'utilisation",
        value=(
            "`!translate fr Hello world`\n"
            "`!translate japonais Bonjour`\n"
            "`!translate zh-cn Good morning`\n"
            "`!tl de Je suis content`"
        ),
        inline=False,
    )
    embed.set_footer(text="Liste complète : https://cloud.google.com/translate/docs/languages")
    await ctx.send(embed=embed)


@bot.command(name="help_translate", aliases=["thelp", "aide"])
async def help_cmd(ctx: commands.Context):
    """!help_translate — Aide complète."""
    embed = discord.Embed(
        title="🌐 Bot de Traduction — Aide",
        description="Traduction gratuite via Google Translate, sans aucune clé API.",
        color=0x5865F2,
    )
    embed.add_field(
        name="📋 Commandes",
        value=(
            "`!translate <langue> <texte>` — Traduit un texte\n"
            "`!tl <langue> <texte>` — Alias court\n"
            "`!detect <texte>` — Détecte la langue\n"
            "`!languages` — Liste des langues\n"
            "`!setlang <langue>` — Langue par défaut du channel\n"
            "`!mirror <#source> <#cible> <langue>` — Miroir automatique\n"
            "`!unmirror <#source>` — Désactive le miroir\n"
            "`!mirrors` — Liste les miroirs actifs\n"
            "`!help_translate` — Cette aide\n"
        ),
        inline=False,
    )
    embed.add_field(
        name="🌐 Réaction automatique",
        value="Réagis avec **🌐** sur n'importe quel message pour le traduire dans la langue par défaut du channel (français par défaut).",
        inline=False,
    )
    embed.add_field(
        name="💡 Exemples",
        value=(
            "`!translate en Bonjour tout le monde !`\n"
            "`!tl ja Hello World`\n"
            "`!detect Ciao come stai?`\n"
            "`!setlang espagnol`"
        ),
        inline=False,
    )
    embed.set_footer(text="100% gratuit • Aucune clé API requise • Propulsé par Google Translate")
    await ctx.send(embed=embed)


# ─── LANCEMENT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if DISCORD_TOKEN == "VOTRE_TOKEN_DISCORD_ICI":
        print("⚠️  Configure ta variable d'environnement DISCORD_TOKEN !")
        print("   Linux/Mac : export DISCORD_TOKEN='ton_token'")
        print("   Windows   : set DISCORD_TOKEN=ton_token")
        print("   Puis relance : python bot.py")
    else:
        print("🚀 Démarrage du bot...")
        bot.run(DISCORD_TOKEN)
