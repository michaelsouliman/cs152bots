from enum import Enum, auto
import discord
import re

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    AWAITING_ABUSE_TYPE = auto()
    AWAITING_MISINFO_CATEGORY = auto()
    AWAITING_HEALTH_CATEGORY = auto()
    AWAITING_NEWS_CATEGORY = auto()
    REPORT_COMPLETE = auto()
    AWAITING_APPEAL = auto()
    APPEAL_REVIEW = auto()
    AWAITING_USER_CONFIRMATION = auto()
    AWAITING_CONTEXT_CONFIRMATION = auto()
    AWAITING_CONTEXT_TEXT = auto()

class AbuseType(Enum):
    BULLYING = "bullying"
    SUICIDE = "suicide/self-harm" 
    EXPLICIT = "sexually explicit/nudity"
    MISINFORMATION = "misinformation"
    HATE = "hate speech"
    DANGER = "danger"

class MisinfoCategory(Enum):
    HEALTH = "health"
    ADVERTISEMENT = "advertisement"
    NEWS = "news"

class HealthCategory(Enum):
    EMERGENCY = "emergency"
    MEDICAL_RESEARCH = "medical research"
    REPRODUCTIVE = "reproductive healthcare"
    TREATMENTS = "treatments"
    ALTERNATIVE = "alternative medicine"

class NewsCategory(Enum):
    HISTORICAL = "historical"
    POLITICAL = "political"
    SCIENCE = "science"

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.abuse_type = None
        self.misinfo_category = None
        self.specific_category = None
        self.user_context = None

    async def handle_message(self, message):
        if message.content.lower() == self.CANCEL_KEYWORD:
            self.state = State.REPORT_COMPLETE
            return ["Report cancelled."]

        if self.state == State.REPORT_START:
            reply = "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE
            return [reply]

        if self.state == State.AWAITING_MESSAGE:
            m = re.search('/(\d+)/(\d+)/(\d+)', message.content)
            if not m:
                return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return ["It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                self.message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            abuse_type_raw = await self.client.classify_abuse_type(self.message.content)
            self.abuse_type = self.client.normalize_abuse_type(abuse_type_raw)
            if self.abuse_type:
                self.state = State.AWAITING_USER_CONFIRMATION
                return [
                    f"I found this message:",
                    f"```{self.message.author.name}: {self.message.content}```",
                    f"The system classified this message as {self.abuse_type}.",
                    "Do you agree with this classification?\n1. Yes\n2. No"
                ]
            else:
                # If the LLM cannot classify, fall back to manual abuse type selection
                self.state = State.AWAITING_ABUSE_TYPE
                reply = "What type of abuse would you like to report?\n"
                reply += "1. BULLYING\n"
                reply += "2. SUICIDE/SELF-HARM\n"
                reply += "3. SEXUALLY EXPLICIT/NUDITY\n"
                reply += "4. MISINFORMATION\n"
                reply += "5. HATE SPEECH\n"
                reply += "6. DANGER"
                return [
                    f"I found this message:",
                    f"```{self.message.author.name}: {self.message.content}```",
                    reply
                ]

        if self.state == State.AWAITING_USER_CONFIRMATION:
            if message.content.strip() == '1':  # User agrees with classification
                self.state = State.AWAITING_CONTEXT_CONFIRMATION
                # stash everything needed:
                self.pending_report = {
                    'report_type': self.abuse_type,
                    'report_content': self.message.content,
                    'message_author': self.message.author.name
                }
                return ["Do you want to add additional context for why you are reporting this message?\n1. Yes\n2. No"]

            elif message.content.strip() == '2':  # User disagrees with classification
                self.state = State.AWAITING_ABUSE_TYPE
                reply = "What type of abuse would you like to report?\n"
                reply += "1. BULLYING\n"
                reply += "2. SUICIDE/SELF-HARM\n"
                reply += "3. SEXUALLY EXPLICIT/NUDITY\n"
                reply += "4. MISINFORMATION\n"
                reply += "5. HATE SPEECH\n"
                reply += "6. DANGER"
                return [reply]
            else:
                return ["Invalid response. Please reply with 1 for Yes or 2 for No."]

        if self.state == State.AWAITING_ABUSE_TYPE:
            abuse_type = message.content.strip()
            abuse_types = {
                '1': AbuseType.BULLYING,
                '2': AbuseType.SUICIDE,
                '3': AbuseType.EXPLICIT,
                '4': AbuseType.MISINFORMATION,
                '5': AbuseType.HATE,
                '6': AbuseType.DANGER
            }

            if abuse_type not in abuse_types:
                return ["Please select a valid option (1-6) from the list above."]

            self.abuse_type = abuse_types[abuse_type]

            if self.abuse_type == AbuseType.MISINFORMATION:
                self.state = State.AWAITING_MISINFO_CATEGORY
                return ["Please select the misinformation category:\n1. HEALTH\n2. ADVERTISEMENT\n3. NEWS"]
            else:
                self.state = State.AWAITING_CONTEXT_CONFIRMATION
                self.pending_report = {
                    'report_type': self.abuse_type.value.upper(),
                    'report_content': self.message.content,
                    'message_author': self.message.author.name
                }
                return ["Do you want to add additional context for why you are reporting this message?\n1. Yes\n2. No"]
            
        if self.state == State.AWAITING_CONTEXT_CONFIRMATION:
            if message.content.strip() == '1':  # wants to add context
                self.state = State.AWAITING_CONTEXT_TEXT
                return ["Please enter additional context (why you are reporting):"]
            elif message.content.strip() == '2':  # no context
                # call start_moderation_flow without context
                data = self.pending_report
                self.pending_report = None
                self.state = State.REPORT_COMPLETE
                await self.client.start_moderation_flow(
                    report_type=data['report_type'],
                    report_content=data['report_content'],
                    message_author=data['message_author'],
                    user_context=None
                )
                return ["Thank you. Your report has been sent to the moderation team."]
            else:
                return ["Invalid choice. Reply with 1 (Yes) or 2 (No)."]

        if self.state == State.AWAITING_CONTEXT_TEXT:
            ctx_text = message.content.strip()
            data = self.pending_report
            self.pending_report = None
            self.user_context = ctx_text
            self.state = State.REPORT_COMPLETE
            await self.client.start_moderation_flow(
                report_type=data['report_type'],
                report_content=data['report_content'],
                message_author=data['message_author'],
                user_context=ctx_text
            )
            return ["Thank you. Your report and context have been sent to the moderation team."]

        if self.state == State.AWAITING_MISINFO_CATEGORY:
            category = message.content.strip()
            misinfo_categories = {
                '1': MisinfoCategory.HEALTH,
                '2': MisinfoCategory.ADVERTISEMENT,
                '3': MisinfoCategory.NEWS
            }

            if category not in misinfo_categories:
                return ["Please select a valid option (1-3) from the list above."]

            self.misinfo_category = misinfo_categories[category]

            if self.misinfo_category == MisinfoCategory.HEALTH:
                self.state = State.AWAITING_HEALTH_CATEGORY
                return ["Please specify the health misinformation category:\n1. EMERGENCY\n2. MEDICAL RESEARCH\n3. REPRODUCTIVE HEALTHCARE\n4. TREATMENTS\n5. ALTERNATIVE MEDICINE"]
            elif self.misinfo_category == MisinfoCategory.NEWS:
                self.state = State.AWAITING_NEWS_CATEGORY
                return ["Please specify the news category:\n1. HISTORICAL\n2. POLITICAL\n3. SCIENCE"]
            else:  # Advertisement
                self.state = State.REPORT_COMPLETE
                mod_channel = self.client.mod_channels[self.message.guild.id]
                await mod_channel.send(f"ADVERTISING MISINFO:\n{self.message.author.name}: {self.message.content}")
                await self.client.start_moderation_flow(
                    report_type="ADVERTISING MISINFO",
                    report_content=self.message.content,
                    message_author=self.message.author.name
                )
                return ["This has been reported to our ad team."]

        if self.state == State.AWAITING_HEALTH_CATEGORY:
            health_cat = message.content.strip()
            health_categories = {
                '1': HealthCategory.EMERGENCY,
                '2': HealthCategory.MEDICAL_RESEARCH,
                '3': HealthCategory.REPRODUCTIVE,
                '4': HealthCategory.TREATMENTS,
                '5': HealthCategory.ALTERNATIVE
            }

            if health_cat not in health_categories:
                return ["Please select a valid option (1-5) from the list above."]

            self.specific_category = health_categories[health_cat]
            self.state = State.REPORT_COMPLETE
            mod_channel = self.client.mod_channels[self.message.guild.id]
            await mod_channel.send(f"HEALTH MISINFO - {self.specific_category.value.upper()}:\n{self.message.author.name}: {self.message.content}")
            await self.client.start_moderation_flow(
                report_type=f"HEALTH MISINFO - {self.specific_category.value.upper()}",
                report_content=self.message.content,
                message_author=self.message.author.name
            )
            return ["This has been sent to our moderation team."]

        if self.state == State.AWAITING_NEWS_CATEGORY:
            news_cat = message.content.strip()
            news_categories = {
                '1': NewsCategory.HISTORICAL,
                '2': NewsCategory.POLITICAL,
                '3': NewsCategory.SCIENCE
            }

            if news_cat not in news_categories:
                return ["Please select a valid option (1-3) from the list above."]

            self.specific_category = news_categories[news_cat]
            self.state = State.REPORT_COMPLETE
            mod_channel = self.client.mod_channels[self.message.guild.id]
            await mod_channel.send(f"NEWS MISINFO - {self.specific_category.value.upper()}:\n{self.message.author.name}: {self.message.content}")
            await self.client.start_moderation_flow(
                report_type=f"NEWS MISINFO - {self.specific_category.value.upper()}",
                report_content=self.message.content,
                message_author=self.message.author.name
            )
            return ["This has been sent to our team."]

        return []

    async def notify_reported_user(self, user_name, guild, outcome, explanation=None):
        # Find the user object by name in the guild
        user = discord.utils.get(guild.members, name=user_name)
        if user:
            try:
                msg = f"Your message was reviewed by moderators. Outcome: {outcome}."
                if explanation:
                    msg += f"\nReason: {explanation}"
                msg += "\nIf you believe this was a mistake, you may reply to this message to appeal."
                await user.send(msg)
                if outcome == "Post removed.":
                    await self.notify_user_of_appeal_option(user_name, guild, explanation)
            except Exception as e:
                print(f"Failed to DM user {user_name}: {e}")

    def report_complete(self):
        """Returns whether the current report is in a completed state"""
        return self.state == State.REPORT_COMPLETE