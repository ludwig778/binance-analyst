import asyncio
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.contrib.regular_languages.compiler import compile
from prompt_toolkit.contrib.regular_languages.completion import GrammarCompleter
from prompt_toolkit.contrib.regular_languages.lexer import GrammarLexer
from prompt_toolkit.lexers import SimpleLexer
from prompt_toolkit.styles import Style
from tabulate import tabulate

from analyst.adapters.factory import get_adapters
from analyst.bot.http_client import BotHttpClient
from analyst.bot.order_manager import OrderManager
from analyst.bot.strategies.registry import RegisteredStrategy
from analyst.controllers.factory import get_controllers
from analyst.repositories.factory import get_repositories
from analyst.settings import get_settings

if TYPE_CHECKING:
    from prompt_toolkit.contrib.regular_languages.compiler import _CompiledGrammar


class PromptContext:
    prompt_string: str = ""
    completer: _CompiledGrammar
    lexer: GrammarLexer
    style: Style

    def __init__(self, http_client):
        self.http_client = http_client

        self.session = PromptSession()

    async def create_prompt(self, context_class, *args, **kwargs):
        return await context_class(self.http_client).run(*args, **kwargs)

    async def prompt(self, prompt_string="", completer=None):
        return await self.session.prompt_async(
            prompt_string or self.prompt_string,
            completer=completer or self._get_completer(),
            lexer=self._get_lexer(),
            style=self._get_style(),
            complete_while_typing=True,
        )

    def _get_completer(self):
        return self.completer

    def _get_lexer(self):
        return self.lexer

    def _get_style(self):
        return self.style


class TableDisplay:
    @staticmethod
    def display_orders(orders):
        table = []
        last_bought = defaultdict(Decimal)

        for order in orders:
            gained = None
            amount = order.price * order.executed_quantity

            if order.status == "NEW":
                took = datetime.now() - order.created_at
            else:
                took = order.updated_at - order.created_at

            if order.side == "BUY":
                last_bought[order.symbol] += order.price * order.executed_quantity
            elif order.side == "SELL" and order.is_filled():
                gained = f"{((amount / last_bought[order.symbol]) - 1) * 100:.2f}%"

            table.append(
                {
                    "id": order.id,
                    "side": order.side,
                    "status": order.status,
                    "price": f"{order.price:10f}",
                    "as base": f"{order.price * order.requested_quantity:.8f}",
                    "as quote": order.requested_quantity,
                    "filled": f"{order.filled_at():.1f}%",
                    "gained": gained,
                    "took": took - timedelta(microseconds=took.microseconds),
                }
            )
            if order.side == "SELL" and order.is_filled():
                last_bought[order.symbol] = Decimal()

        print("=" * 45)
        print(tabulate(table, headers="keys"))

    @staticmethod
    def display_strategies_orders(strategies_orders):
        strategies = [
            {
                "id": str(strategy.id)[:8],
                "name": strategy.name,
                "version": strategy.version,
                "key": strategy.get_key(),
                "flags": strategy.flags.to_simple_str(),
                "state": strategy.state.name,
                "orders": len([order for order in orders if not order.is_cancelled()]),
            }
            for strategy, orders in strategies_orders.items()
        ]

        print(tabulate(strategies, headers="keys"))

    @staticmethod
    def display_strategy(strategy):
        print(tabulate(strategy, headers="simple"))

    @staticmethod
    def display_account(account):
        print(tabulate(account, headers="keys"))


class ArgPrompt(PromptContext):
    async def run(self, args_meta, pairs=None):
        args = {}

        for arg_name, arg_cls in args_meta.items():
            override_completer = None
            if arg_name == "symbol" and pairs:
                override_completer = WordCompleter(pairs)

            while True:
                try:
                    result = await self.prompt(
                        f"{arg_name} ({arg_cls.__name__}) : ", completer=override_completer
                    )

                    if arg_cls is str and result == "":
                        print("cannot")

                        continue
                    elif arg_cls is Decimal:
                        decimal = arg_cls(result)

                        if decimal <= 0:
                            print("decimal values must be positive")

                            continue

                    args[arg_name] = result

                    break
                except Exception as exc:
                    print(str(exc))
                except KeyboardInterrupt:
                    return

        return args


class MainPrompt(PromptContext):
    prompt_string = "lmao # "
    grammar = compile(
        r"""
        (\s* (?P<operator>add) \s* (?P<strategy_tuple>[a-z0-9:_]*) \s*) |
        (\s* (?P<operator>(stop|summarize|remove)) \s* (?P<strategy_id>[0-9a-zA-Z]*) \s*) |
        (\s* (?P<operator>(account|list|ping|quit)) \s*)
    """
    )
    lexer = GrammarLexer(
        grammar,
        lexers={
            "operator": SimpleLexer("class:operator"),
            "symbol": SimpleLexer("class:symbol"),
        },
    )
    style = Style.from_dict(
        {
            "": "#69bee6 bold",
            "operator": "#e669be bold",
            "symbol": "#bee669 bold",
        }
    )

    def _get_completer(self):
        return GrammarCompleter(
            self.grammar,
            {
                "operator": WordCompleter(
                    ["add", "account", "ping", "stop", "list", "remove", "summarize", "quit"]
                ),
                "symbol": WordCompleter(self.pairs),
                "strategy_tuple": WordCompleter(RegisteredStrategy.instances.keys()),
                "strategy_id": WordCompleter(self._get_strategies_by_truncated_ids().keys()),
            },
        )

    def _get_strategies_by_truncated_ids(self):
        return {str(strategy.id)[:8]: strategy for strategy in self.strategies_orders.keys()}

    async def load_running_strategies_and_orders(self):
        self.strategies_orders = await self.http_client.get_running_strategies()

    async def load_pairs(self):
        self.pairs = await self.http_client.get_pairs()

    async def run(self):
        await self.load_pairs()
        await self.load_running_strategies_and_orders()

        while True:
            try:
                result = await self.prompt()
            except KeyboardInterrupt:
                print("Quitting...\n")

                break

            if not result:
                response = await self.http_client.test()

                print("none")
                print(response)

                continue

            elif matches := self.grammar.match(result):
                vars = matches.variables()

                strategy_id = vars["strategy_id"]

                if vars["operator"] == "add":
                    strategy_tuple = vars["strategy_tuple"]

                    name, version = strategy_tuple.split(":")

                    strategy_cls = RegisteredStrategy.get_class(name, version)

                    if not strategy_cls:
                        print(f"No strategy found for {strategy_tuple}, reload the prompt")
                        print()

                        continue

                    args = await self.create_prompt(
                        ArgPrompt, strategy_cls.get_args_meta(), pairs=self.pairs
                    )

                    if not args:
                        print("Skipping strategy creation")

                    else:
                        response = await self.http_client.add_strategy(name, version, args)

                        if response["status"] == "ok":
                            print("Strategy added")
                        else:
                            print("Strategy add failed: ", response["message"])

                        await self.load_running_strategies_and_orders()

                elif vars["operator"] == "ping":
                    response = await self.http_client.ping()

                    print(response["status"])

                elif vars["operator"] == "list":
                    await self.load_running_strategies_and_orders()

                    TableDisplay.display_strategies_orders(self.strategies_orders)

                elif vars["operator"] == "account":
                    account = await self.http_client.get_account()

                    TableDisplay.display_account(account)

                elif vars["operator"] == "summarize":
                    await self.load_running_strategies_and_orders()

                    strategy = self._get_strategies_by_truncated_ids()[strategy_id]

                    orders = self.strategies_orders[strategy]

                    TableDisplay.display_orders(orders)

                elif vars["operator"] == "remove":
                    strategy = self._get_strategies_by_truncated_ids()[strategy_id]

                    response = await self.http_client.remove_strategy(strategy)

                    if response["status"] == "ok":
                        await self.load_running_strategies_and_orders()

                        print("Strategy removed")
                    else:
                        print("Strategy remove failed: ", response["message"])

                elif vars["operator"] == "stop":
                    strategy = self._get_strategies_by_truncated_ids()[strategy_id]

                    response = await self.http_client.stop_strategy(strategy)

                    if response["status"] == "ok":
                        await self.load_running_strategies_and_orders()

                        print("Strategy stop sended")
                    else:
                        print("Strategy stop send failed: ", response["message"])

                elif vars["operator"] == "quit":
                    break

                else:
                    print(f"{result=}", vars)

            else:
                print("Invalid command")

            print()


async def bot_prompt():
    settings = get_settings()
    adapters = await get_adapters(settings=settings)
    repositories = get_repositories(settings=settings, adapters=adapters)
    controllers = get_controllers(adapters=adapters, repositories=repositories)

    order_manager = OrderManager(
        controllers=controllers,
    )
    await order_manager.setup()

    # bot = Runner(
    #    controllers=controllers,
    #    order_manager=order_manager
    # )
    # http_server = BotHttpServer(settings.bot, bot, controllers)
    http_client = BotHttpClient(settings.bot)

    try:
        try:
            # await http_server.run()
            await http_client.login()
            await asyncio.gather(
                # http_server.run(),
                # bot.run(),
                MainPrompt(http_client=http_client).run(),
            )
        except Exception:
            print(traceback.print_exc())
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_prompt())
