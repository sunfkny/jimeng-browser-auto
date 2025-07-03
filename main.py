import enum
import json
import time

from DrissionPage import ChromiumPage
from DrissionPage._units.listener import DataPacket
from loguru import logger


class GenerateStatus(enum.Enum):
    Unknown = -1
    Init = 0
    PreTnsCheckNotPass = 10
    SubmitOk = 20
    FinalGenerateFail = 30
    PostTnsCheckNotPass = 40
    FinalSuccess = 50
    Deleted = 100

    @staticmethod
    def try_parse(status: int):
        try:
            return GenerateStatus(status)
        except ValueError:
            return GenerateStatus.Unknown


def main(prompt: str, use_get_asset_list: bool = True):
    """
    Params:
        prompt: str 提示词
        use_get_asset_list: bool 是否使用 列表api返回值, 启用可能速度更快, 但是可能获取相同prompt的旧图片
    """
    prompt = prompt.replace("\n", " ")

    page = ChromiumPage()
    logger.info("Open page")
    page.get("https://jimeng.jianying.com/ai-tool/home")

    logger.info("Check login")
    while page.eles("css:#SiderMenuLogin"):
        time.sleep(1)
        logger.info("waiting for login...")

    page.listen.start("/mweb/v1/")

    logger.info("Input text")
    page.ele("css:textarea").input(prompt).input("\n")

    logger.info("Waiting for generate...")
    task_submit_id: str | None = None
    for packet in page.listen.steps(timeout=5 * 60):
        assert isinstance(packet, DataPacket)
        logger.debug(packet.url)

        if packet.url.startswith(
            "https://jimeng.jianying.com/mweb/v1/aigc_draft/generate"
        ):
            response = packet.response.body
            assert isinstance(response, dict)
            if response["ret"] != "0":
                logger.error(response)
            else:
                image = response["data"]["aigc_data"]
                submit_id = image["submit_id"]
                task_submit_id = submit_id
                logger.info(f"{task_submit_id=}")

        if use_get_asset_list and packet.url.startswith(
            "https://jimeng.jianying.com/mweb/v1/get_asset_list"
        ):
            response = packet.response.body
            assert isinstance(response, dict)
            if response["ret"] != "0":
                logger.error(response)
            else:
                asset_list = response["data"]["asset_list"]
                for asset in asset_list:
                    image = asset["image"]
                    history_group_key = image["history_group_key"]
                    submit_id = image["submit_id"]
                    logger.debug(f"{submit_id=} {history_group_key=}")
                    if task_submit_id == submit_id:
                        status = GenerateStatus.try_parse(image["status"])
                        logger.info(f"{status=}")
                        if status == GenerateStatus.FinalSuccess:
                            return submit_id, image
                        elif status == GenerateStatus.SubmitOk:
                            logger.info("Waiting for SubmitOk")

        if packet.url.startswith(
            "https://jimeng.jianying.com/mweb/v1/get_history_by_ids"
        ):
            response = packet.response.body
            assert isinstance(response, dict)
            if response["ret"] != "0":
                logger.error(response)
            else:
                data = response["data"]
                assert isinstance(data, dict)
                image_list = list[dict](data.values())
                for image in image_list:
                    history_group_key = image["history_group_key"]
                    submit_id = image["submit_id"]
                    logger.debug(f"{submit_id=} {history_group_key=}")
                    if task_submit_id == submit_id:
                        status = GenerateStatus.try_parse(image["status"])
                        logger.info(f"status={status.name}")
                        if status == GenerateStatus.FinalSuccess:
                            return submit_id, image
                        elif status == GenerateStatus.SubmitOk:
                            logger.info("Waiting for SubmitOk")

    raise RuntimeError("Failed to generate image")


if __name__ == "__main__":
    submit_id, image = main(
        "二次元少女在樱花树下读书，水手服随风飘动，粉紫色晚霞天空，新海诚风格，赛璐珞上色，8k分辨率，景深虚化"
    )

    with open(f"{submit_id}.json", "w", encoding="utf8") as f:
        f.write(json.dumps(image, indent=4, ensure_ascii=False))
