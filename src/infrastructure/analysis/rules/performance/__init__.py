"""Performance analysis rules."""

from .inefficient_string_concat import InefficientStringConcatRule
from .n_plus_one import NPlusOneRule
from .inefficient_list import InefficientListRule
from .recursive_without_memo import RecursiveWithoutMemoRule
from .inefficient_comprehension import InefficientComprehensionRule
from .regex_in_loop import RegexInLoopRule
from .duplicate_queries import DuplicateQueriesRule
from .sync_in_async import SyncInAsyncRule
from .unnecessary_all import UnnecessaryAllRule
from .lazy_vs_eager import LazyVsEagerRule
from .unnecessary_conversion import UnnecessaryConversionRule
from .inefficient_dict import InefficientDictRule
from .glob_instead_of_listdir import GlobVsListdirRule
from .yield_vs_return import YieldVsReturnRule
from .inefficient_set_ops import InefficientSetOpsRule

__all__ = [
    "InefficientStringConcatRule",
    "NPlusOneRule",
    "InefficientListRule",
    "RecursiveWithoutMemoRule",
    "InefficientComprehensionRule",
    "RegexInLoopRule",
    "DuplicateQueriesRule",
    "SyncInAsyncRule",
    "UnnecessaryAllRule",
    "LazyVsEagerRule",
    "UnnecessaryConversionRule",
    "InefficientDictRule",
    "GlobVsListdirRule",
    "YieldVsReturnRule",
    "InefficientSetOpsRule",
]
