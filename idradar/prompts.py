"""中英提示词集中保存；中文、英文起名原文均与设计逐字比对。"""

NAMING_PROMPT = """你是我的起名顾问。我要一个在 B站、抖音、小红书、微信视频号、X、GitHub 通用的昵称，用来做个人 IP，要让人一提到这个名字就想到我。

请先不要给名字。一次性问我下面 5 个问题，等我回答完再推荐：
1. 你希望别人怎么称呼你？（真名、英文名、常用称呼，只说你愿意公开的部分）
2. 你是谁？身份、专业或工作、正在做的事。
3. 你的性格和说话风格是怎样的？
4. 你希望别人提到这个名字时，想到你的什么？
5. 你喜欢或想避开什么风格？有没有想放进名字的元素（宠物、爱好、口头禅、梗）？

收到回答后，推荐 15 个名字。要求：
- 和我本人强相关，别人没法照抄；好记、好念、好搜；
- 中文名 2～8 个字，可以中英混合；不要用 · _ - 等符号，很多平台不允许；
- 每个名字配一个英文 handle，用于 X 和 GitHub：只用小写字母和数字（不要下划线和连字符），5～15 位；
- handle 要像英文昵称一样好念，可以用英文名加姓、英文名加缩写或一个英文词，不要把中文名整串转成拼音。

最后把 15 个名字放进一个代码块，每行一个，格式严格为：
名字 | handle
代码块外面再用一两句话解释每个名字的含义和梗。"""

HANDLE_PROMPT = """给下面每个名字配一个英文 handle，用于 X 和 GitHub：只用小写字母和数字（不要下划线和连字符），5～15 位，像英文昵称一样好念，不要把中文整串转成拼音。放进一个代码块，每行一个，格式严格为：
名字 | handle"""

NAMING_PROMPT_EN = """You are my naming consultant. I need one name to use across X, GitHub and other social platforms for my personal brand, so that people think of me when they hear it.

Don't suggest any names yet. First ask me these 5 questions all at once, then wait for my answers:
1. What should people call you? (real name, English name, nickname: only what you're happy to make public)
2. Who are you? Your role, field or job, and what you're working on.
3. What are your personality and way of talking like?
4. When people hear this name, what should they think of?
5. What styles do you like or want to avoid? Anything you'd like in the name (pets, hobbies, catchphrases, in-jokes)?

After I answer, suggest 15 names. Requirements:
- Strongly tied to me and hard to copy; easy to remember, say and search;
- Display names up to 20 characters; avoid symbols such as · _ - because many platforms don't allow them;
- Give each name a handle for X and GitHub: lowercase letters and digits only (no underscores or hyphens), 5 to 15 characters, easy to say like a real nickname.

Finally put all 15 names in one code block, one per line, in exactly this format:
Name | handle
Outside the code block, explain each name's meaning in a sentence or two."""

HANDLE_PROMPT_EN = """Give each name below an English handle for X and GitHub: lowercase letters and digits only (no underscores or hyphens), 5 to 15 characters, easy to say like a real nickname. Do not turn a Chinese name into a long string of pinyin. Put the results in one code block, one per line, in exactly this format:
Name | handle"""

PROMPTS = {"zh": {"naming": NAMING_PROMPT, "handle": HANDLE_PROMPT}, "en": {"naming": NAMING_PROMPT_EN, "handle": HANDLE_PROMPT_EN}}


def naming_prompt():
    from .i18n import language
    return PROMPTS[language()]["naming"]


def handle_prompt(lang=None):
    from .i18n import language
    return PROMPTS[language(lang)]["handle"]
