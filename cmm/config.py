import requests
from os import environ
from flask import request
from sqlalchemy import exc
from http import HTTPStatus
from common import _extract_token
from flask_restx import Resource, Namespace, fields

ns_config = Namespace("config",description="Obtem as configuracoes do sistema")

#API Models
cfg_model = ns_config.model(
    "Config",{
        "ai_model": fields.String,
        "ai_api_key": fields.String,
        "company_custom":fields.Boolean,
        "company_name":fields.String,
        "company_logo":fields.String,
        "url_instagram":fields.String,
        "url_facebook":fields.String,
        "url_linkedin":fields.String,
        "max_upload_files":fields.Integer,
        "max_upload_images":fields.Integer,
        "use_url_images":fields.Boolean,
        "pagination_size":fields.Integer,
        "email_brevo_api_key": fields.String,
        "email_from_name": fields.String,
        "email_from_value": fields.String
    }
)

@ns_config.route("/")
class ConfigList(Resource):
    @ns_config.response(HTTPStatus.OK,"Obtem as informações de configuração do tenant")
    @ns_config.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    def get(self):
        try:
            resp = requests.get(str(environ.get("F2B_SMC_URL"))+"config/"+str(request.headers.get("x-customer")))
            if resp.status_code == HTTPStatus.OK.value:
                cfg = resp.json()
                return {
                    "ai_model": cfg["ai_model"],
                    "ai_api_key": cfg["ai_api_key"],
                    "company_custom": cfg["company_custom"],
                    "company_name": cfg["company_name"],
                    "company_logo": cfg["company_logo"],
                    "url_instagram": cfg["url_instagram"],
                    "url_facebook": cfg["url_facebook"],
                    "url_linkedin": cfg["url_linkedin"],
                    "pagination_size": cfg["pagination_size"],
                    "email_brevo_api_key": cfg["email_brevo_api_key"],
                    "email_from_name": cfg["email_from_name"],
                    "email_from_value": cfg["email_from_value"]
                }
            else:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Impossível buscar as configurações!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_config.response(HTTPStatus.OK,"Salva as informações de configuração do tenant")
    @ns_config.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    def post(self):
        try:
            url = str(environ.get("F2B_SMC_URL"))+"config/"+str(request.headers.get("x-customer"))
            resp = requests.post(url,json=request.get_json())
            if resp.status_code == HTTPStatus.OK.value:
                return True if resp.text.replace("\n","")=="true" else False
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
# colocar busca do aws da receita e tambem do brasil_aberto