from cmm.ai import ns_ai
from flask_restx import Api
from flask import Blueprint
from cmm.email import ns_email
from cmm.products import ns_prod
from cmm.upload import ns_upload
from cmm.config import ns_config
from cmm.reports import ns_report
from cmm.products_type import ns_type
from cmm.products_grid import ns_gprod
from cmm.translate_sizes import ns_size
from cmm.products_model import ns_model
from cmm.legal_entities import ns_legal
from cmm.products_category import ns_cat
from cmm.translate_colors import ns_color
from cmm.measure_unit import ns_measure_unit
from cmm.integration import ns_integra
from common import _before_execute


""" Módulo Common entre os sistemas
    Módulo que unificará os sistemas através de uma única API com coisas que são comuns em todas as etapas

Keyword arguments: usuarios, produtos
"""

#nss = [ns_user]
nss = [ns_ai,
       ns_cat,
       ns_color,
       ns_config,
       ns_gprod,
       ns_legal,
       ns_measure_unit,
       ns_model,
       ns_prod,
       ns_report,
       ns_size,
       ns_type,
       ns_upload,
       ns_email,
       ns_integra
    ]


bp_cmm = Blueprint("cmm",__name__,url_prefix="/cmm/api/")
@bp_cmm.before_request
def before_request():
    """ Executa antes de cada requisição """
    _before_execute(True)

api = Api(bp_cmm,
    version="1.0",
    title="API Fast2Bee",
    description="Uma API REST para o sistema CLM (Módulo Common)",
    contact_email="e.rivas@fast2bee.com",
    contact="Fast2Bee",
    contact_url="http://www.fast2bee.com")

for ns in nss:
    api.add_namespace(ns)