from .bot import ReminderBot
from .config import load_config


def main() -> None:
    config = load_config()
    ReminderBot(config).run(config.discord_token, root_logger=True)


if __name__ == "__main__":
    main()
