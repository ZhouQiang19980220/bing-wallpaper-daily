import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

# === Constants ===
BING_BASE_URL = "https://www.bing.com"
BING_API_URL = "https://www.bing.com/HPImageArchive.aspx"


# === Helper Functions ===
def get_project_root(
    anchor_files: tuple = (".git", "pyproject.toml", "requirements.txt"),
) -> Path:
    """
    通过向上寻找特征文件来确定项目根目录。
    """
    current_path = Path(__file__).resolve()

    for path in [current_path] + list(current_path.parents):
        for anchor in anchor_files:
            if (path / anchor).exists():
                return path

    return current_path.parent


# === Data Structures ===
@dataclass
class WallpaperData:
    """数据类：用于承载解析后的壁纸元数据"""

    date_str: str
    image_url: str
    title: str
    copyright: str
    filename: str


# === Main Class ===
class BingWallpaperCollector:
    """Bing 壁纸收集器核心类"""

    def __init__(self, relative_output_dir: str, market: str = "zh-CN"):
        self.market = market
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            }
        )

        # 1. 确定项目根目录
        self.project_root: Path = get_project_root()
        logger.debug(f"📂 Detected Project Root: {self.project_root}")

        # 2. 确定 README 和 输出目录
        self.readme_path = self.project_root / "README.md"
        # 接收字符串，内部转为 Path，逻辑更自洽
        self.output_dir = self.project_root / relative_output_dir

    def run(self) -> None:
        """执行收集流程的主入口"""
        logger.info(f"🚀 Starting collector for market: {self.market}")

        try:
            metadata = self._fetch_metadata()
            if not metadata:
                logger.warning("No metadata fetched. Exiting.")
                return

            # 创建年份文件夹
            year_dir = self.output_dir / str(date.today().year)
            year_dir.mkdir(parents=True, exist_ok=True)

            save_path = year_dir / metadata.filename

            if save_path.exists():
                logger.info(f"⚠️ File already exists: {save_path}. Skipping download.")
                return

            self._download_image(metadata.image_url, save_path)
            self._update_readme(metadata)

        except Exception as e:
            logger.exception(f"🔥 Critical error in execution: {e}")
            sys.exit(1)

    def _fetch_metadata(self) -> Optional[WallpaperData]:
        params = {"format": "js", "idx": 0, "n": 1, "mkt": self.market}

        try:
            logger.debug(f"Fetching metadata from {BING_API_URL}...")
            resp = self.session.get(BING_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            image_data = data["images"][0]
            url_suffix = image_data["url"]
            copyright_text = image_data["copyright"]
            date_str = image_data["enddate"]

            full_url = f"{BING_BASE_URL}{url_suffix}"
            title_clean = self._clean_filename(copyright_text.split("(")[0].strip())
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            filename = f"{formatted_date}_{title_clean}.jpg"

            logger.info(f"📸 Metadata fetched: {filename}")

            return WallpaperData(
                date_str=formatted_date,
                image_url=full_url,
                title=copyright_text,
                copyright=copyright_text,
                filename=filename,
            )

        except (requests.RequestException, KeyError, IndexError) as e:
            logger.error(f"Error fetching/parsing metadata: {e}")
            return None

    def _download_image(self, url: str, save_path: Path) -> None:
        try:
            logger.debug(f"Downloading image from {url}...")
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()

            with open(save_path, "wb") as f:
                f.write(resp.content)
            logger.success(f"✅ Image saved: {save_path}")

        except requests.RequestException as e:
            logger.error(f"Failed to download image: {e}")
            raise

    def _update_readme(self, data: WallpaperData) -> None:
        content = f"""# 🏞️ Bing Daily Wallpaper

> 🤖 Auto-collected by GitHub Actions.
> Market: {self.market}

## 📅 Today ({data.date_str})

![{data.title}]({data.image_url})

> **{data.copyright}**

## 🗄️ Archives
- [View Archives](archives/)
"""
        try:
            with open(self.readme_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("📝 README.md updated.")
        except IOError as e:
            logger.error(f"Failed to write README.md: {e}")

    @staticmethod
    def _clean_filename(text: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "", text).strip()


def parse_args():
    parser = argparse.ArgumentParser(description="Bing Wallpaper Collector")
    parser.add_argument(
        "--output", type=str, default="archives", help="Relative output directory name"
    )
    parser.add_argument(
        "--market", type=str, default="zh-CN", help="Bing market (e.g., zh-CN, en-US)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    )

    args = parse_args()

    # 修复点：直接传 args.output (str)，让类内部去和 project_root 拼接
    # 修复点：参数名改为 relative_output_dir，与 __init__ 对应
    collector = BingWallpaperCollector(
        relative_output_dir=args.output, market=args.market
    )
    collector.run()
