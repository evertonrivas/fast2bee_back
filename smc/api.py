from flask import Blueprint
from flask_restx import Api
from smc.plan import ns_plan
from smc.users import ns_user
from smc.cities import ns_city
from smc.config import ns_config
from smc.payment import ns_payment
from smc.countries import ns_country
from smc.customer import ns_customer
from smc.state_regions import ns_state_region
from common import _before_execute

nss = [ns_customer,
       ns_plan,
       ns_payment,
       ns_user,
       ns_city,
       ns_country,
       ns_state_region,
       ns_config]

bp_smc = Blueprint("smc",__name__,url_prefix="/smc/api/")

@bp_smc.before_request
def before_request():
    """ Executa antes de cada requisição """
    _before_execute()

api = Api(bp_smc,
    version="1.0",
    title="API Fast2Bee",
    description="Uma API REST para o sistema Módulo SMC (System Management Customers)",
    contact_email="e.rivas@fast2bee.com",
    contact="Fast2Bee",
    contact_url="http://www.fast2bee.com")

for ns in nss:
    api.add_namespace(ns)