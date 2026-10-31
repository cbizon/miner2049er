from importlib import import_module

from miner2049er.benchmark_dashboard import install_benchmark_dashboard
from miner2049er.gandalf_runtime import configure_local_biolink
from miner2049er.rule_viewer import install_rule_viewer

configure_local_biolink()
APP = import_module("gandalf.server").APP
install_rule_viewer(APP)
install_benchmark_dashboard(APP)


__all__ = ["APP"]
