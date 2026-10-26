"""视频号只提供手动查询指引。"""

from ..i18n import t
from .base import Checker, Result


class WeixinChannelsChecker(Checker):
    id, label, mode = "weixin_channels", t('platform.weixin_channels'), "manual"

    async def check(self, name, handle):
        return Result("manual", search_url="https://channels.weixin.qq.com/", note=t('channels.note'))
