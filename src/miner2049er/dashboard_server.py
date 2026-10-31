from fastapi import FastAPI

from miner2049er.benchmark_dashboard import install_benchmark_dashboard

APP = FastAPI(title="Miner2049er benchmark dashboard")
install_benchmark_dashboard(APP)

__all__ = ["APP"]
