from __future__ import annotations

from dataclasses import dataclass, field

import yaml


@dataclass
class PathsConfig:
    input_csv: str = ""
    output_dir: str = "output"
    message_template: str = "templates/message_template.txt"


@dataclass
class WholesaleSelectors:
    product_name: str = ""
    price: str = ""
    sizes: str = ""
    colors: str = ""
    detail_images: str = ""


@dataclass
class LoginForm:
    id_field: str = "mb_id"
    pw_field: str = "mb_password"


@dataclass
class WholesaleConfig:
    base_url: str = ""
    login_url: str = ""
    selectors: WholesaleSelectors = field(default_factory=WholesaleSelectors)
    login_form: LoginForm = field(default_factory=LoginForm)
    request_delay_seconds: float = 1.0
    username: str = ""
    password: str = ""


@dataclass
class SystemConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    wholesale: WholesaleConfig = field(default_factory=WholesaleConfig)


def load_config(
    settings_path: str = "config/settings.yaml",
) -> SystemConfig:
    """YAML 설정 파일을 로드한다. 인증 정보는 GUI에서 주입한다."""
    from src.resource import resource_path

    config = SystemConfig()

    settings_file = resource_path(settings_path)
    if settings_file.exists():
        with open(settings_file) as f:
            data = yaml.safe_load(f) or {}
        _apply_settings(config, data)

    config.paths.message_template = str(resource_path(config.paths.message_template))

    return config


def _apply_settings(config: SystemConfig, data: dict) -> None:
    paths = data.get("paths", {})
    if paths.get("input_csv"):
        config.paths.input_csv = paths["input_csv"]
    if paths.get("output_dir"):
        config.paths.output_dir = paths["output_dir"]
    if paths.get("message_template"):
        config.paths.message_template = paths["message_template"]

    ws = data.get("wholesale", {})
    if ws.get("base_url"):
        config.wholesale.base_url = ws["base_url"]
    if ws.get("login_url"):
        config.wholesale.login_url = ws["login_url"]
    if ws.get("request_delay_seconds") is not None:
        config.wholesale.request_delay_seconds = float(ws["request_delay_seconds"])

    selectors = ws.get("selectors", {})
    for key in ("product_name", "price", "sizes", "colors", "detail_images"):
        if selectors.get(key):
            setattr(config.wholesale.selectors, key, selectors[key])

    login_form = ws.get("login_form", {})
    if login_form.get("id_field"):
        config.wholesale.login_form.id_field = login_form["id_field"]
    if login_form.get("pw_field"):
        config.wholesale.login_form.pw_field = login_form["pw_field"]


