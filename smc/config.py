# from auth import auth
from flask import request
from http import HTTPStatus
from f2bconfig import DashboardImage, DashboardImageColor
from models.helpers import db # , _get_params
from sqlalchemy import Select, exc
from models.public import SysConfig
from flask_restx import Resource,Namespace,fields

ns_config = Namespace("config",description="Operações para manipular as configuracoes do sistema")

#API Models
config_pag_model = ns_config.model(
    "Pagination",{
        "registers": fields.Integer,
        "page": fields.Integer,
        "per_page": fields.Integer,
        "pages": fields.Integer,
        "has_next": fields.Boolean
    }
)
config_model = ns_config.model(
    "City",{
        "id": fields.Integer,
        "name": fields.String
    }
)

config_return = ns_config.model(
    "CityReturn",{
        "pagination": fields.Nested(config_pag_model),
        "data": fields.List(fields.Nested(config_model))
    }
)

# @ns_config.route("/")
# class CategoryList(Resource):
    # @ns_config.response(HTTPStatus.OK,"Obtem a listagem de configuracoes",config_return)
    # @ns_config.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    # @ns_config.param("page","Número da página de registros","query",type=int,required=True,default=1)
    # @ns_config.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    # @ns_config.param("query","Texto para busca","query")
    # @auth.login_required
    # def get(self):
    #     pag_num  = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
    #     pag_size = int(str(environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))

    #     try:
    #         params    = _get_params(request.args.get("query"))
    #         if params is not None:
    #             direction = asc if not hasattr(params,'order') else asc if str(params.order).upper()=='ASC' else desc
    #             order_by  = 'id' if not hasattr(params,'order_by') else params.order_by
    #             search    = None if not hasattr(params,"search") else params.search
    #             list_all  = False if not hasattr(params,"list_all") else params.list_all
    #             filter_country = None if not hasattr(params,"country") else params.country

    #         rquery = Select(SysStateRegions.id,
    #                         SysStateRegions.id_country,
    #                         SysStateRegions.name,
    #                         SysStateRegions.acronym)\
    #                         .select_from(SysStateRegions)\
    #                         .order_by(direction(getattr(SysStateRegions,order_by)))
            
    #         if search is not None:
    #             rquery = rquery.where(or_(
    #                 SysStateRegions.name.like("%{}%".format(search)),
    #                 SysStateRegions.acronym.like("%{}%".format(search))
    #             ))

    #         if filter_country is not None:
    #             if str(filter_country).find(",")==-1:
    #                 rquery = rquery.where(SysStateRegions.id_country==filter_country)
    #             else:
    #                 rquery = rquery.where(SysStateRegions.id_country.in_(filter_country))

    #         if not list_all:
    #             pag = db.paginate(rquery,page=pag_num,per_page=pag_size)
    #             rquery = rquery.limit(pag_size).offset((pag_num - 1) * pag_size)

    #             retorno = {
	# 				"pagination":{
	# 					"registers": pag.total,
	# 					"page": pag_num,
	# 					"per_page": pag_size,
	# 					"pages": pag.pages,
	# 					"has_next": pag.has_next
	# 				},
	# 				"data":[{
	# 					"id": m.id,
    #                     "id_country": m.id_country,
	# 					"name": m.name,
    #                     "acronym": m.acronym
	# 				} for m in db.session.execute(rquery)]
	# 			}
    #         else:
    #             retorno = [{
	# 					"id": m.id,
    #                     "id_country": m.id_country,
	# 					"name": m.name,
    #                     "acronym": m.acronym
	# 				} for m in db.session.execute(rquery)]
    #         return retorno
    #     except exc.SQLAlchemyError as e:
    #         return {
    #             "error_code": e.code,
    #             "error_details": e._message(),
    #             "error_sql": e._sql_message()
    #         }

    # @ns_config.response(HTTPStatus.OK,"Cria uma nova cidade")
    # @ns_config.response(HTTPStatus.BAD_REQUEST,"Falha ao criar novo registro!")
    # @ns_config.doc(body=config_model)
    # @auth.login_required
    # def post(self):
    #     try:
    #         req = request.get_json()
    #         reg:SysStateRegions = SysStateRegions()
    #         reg.name = req["name"]
    #         reg.id_country = req["id_country"]
    #         db.session.add(reg)
    #         db.session.commit()
    #         return reg.id
    #     except exc.SQLAlchemyError as e:
    #         return {
    #             "error_code": e.code,
    #             "error_details": e._message(),
    #             "error_sql": e._sql_message()
    #         }

@ns_config.route("/<string:id>")
class ConfigApi(Resource):
    @ns_config.response(HTTPStatus.OK,"Obtem um registro de uma nova cidade",config_model)
    @ns_config.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    # @auth.login_required
    def get(self,id:str):
        try:
            cfg = db.session.execute(Select(SysConfig).where(SysConfig.id_customer==id)).first()
            if cfg is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Configuração não encontrada!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST
            else:
                if cfg[0].dashboard_config=='M':
                    dash_image = DashboardImage.MEN.value
                    dash_color = DashboardImageColor.MEN.value
                if cfg[0].dashboard_config=='W':
                    dash_image = DashboardImage.WOMEN.value
                    dash_color = DashboardImageColor.WOMEN.value
                if cfg[0].dashboard_config=='H':
                    dash_image = DashboardImage.WHEAT.value
                    dash_color = DashboardImageColor.WHEAT.value
                if cfg[0].dashboard_config=='D':
                    dash_image = DashboardImage.DRINK.value
                    dash_color = DashboardImageColor.DRINK.value
                if cfg[0].dashboard_config=='S':
                    dash_image = DashboardImage.SHOES.value
                    dash_color = DashboardImageColor.SHOES.value
                if cfg[0].dashboard_config=='P':
                    dash_image = DashboardImage.PISTON.value
                    dash_color = DashboardImageColor.PISTON.value
                if cfg[0].dashboard_config=='F':
                    dash_image = DashboardImage.PHARMA.value
                    dash_color = DashboardImageColor.PHARMA.value
                
                return {
                    "id_customer": str(cfg[0].id_customer),
                    "pagination_size": cfg[0].pagination_size,
                    "email_brevo_api_key": cfg[0].email_brevo_api_key,
                    "email_from_name": cfg[0].email_from_name,
                    "email_from_value": cfg[0].email_from_value,
                    "flimv_model": cfg[0].flimv_model,
                    "dashboard_config": cfg[0].dashboard_config,
                    "dashboard_image": dash_image,
                    "dashboard_color": dash_color,
                    "ai_model": cfg[0].ai_model,
                    "ai_api_key": cfg[0].ai_api_key,
                    "company_custom": cfg[0].company_custom,
                    "company_name": cfg[0].company_name,
                    "company_logo": cfg[0].company_logo,
                    "url_instagram": cfg[0].url_instagram,
                    "url_facebook": cfg[0].url_facebook,
                    "url_linkedin": cfg[0].url_linkedin,
                    "max_upload_files": cfg[0].max_upload_files,
                    "max_upload_images": cfg[0].max_upload_images,
                    "use_url_images": cfg[0].use_url_images,
                    "track_orders": cfg[0].track_orders,
                    "erp_integration": cfg[0].erp_integration,
                    "erp_url": cfg[0].erp_url,
                    "erp_token": cfg[0].erp_token,
                    "erp_grant_type": cfg[0].erp_grant_type,
                    "erp_client_id": cfg[0].erp_client_id,
                    "erp_client_secret": cfg[0].erp_client_secret,
                    "erp_username": cfg[0].erp_username,
                    "erp_password": cfg[0].erp_password
                }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
            

    @ns_config.response(HTTPStatus.OK,"Atualiza os dados da configuração de um cliente")
    @ns_config.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    # @auth.login_required
    def post(self,id:str):
        try:
            req = request.get_json()
            cfg = db.session.execute(Select(SysConfig).where(SysConfig.id_customer==id)).first()
            if cfg is None:
                return False
            
            reg:SysConfig|None = cfg[0]
            if reg is not None:
                reg.pagination_size     = req["pagination_size"]
                reg.email_brevo_api_key = req["email_brevo_api_key"]
                reg.email_from_name     = req["email_from_name"]
                reg.email_from_value    = req["email_from_value"]
                reg.ai_model            = req["ai_model"]
                reg.ai_api_key          = req["ai_api_key"]
                reg.company_custom      = req["company_custom"]
                reg.company_name        = req["company_name"]
                reg.company_logo        = req["company_logo"]
                reg.url_instagram       = req["url_instagram"]
                reg.url_facebook        = req["url_facebook"]
                reg.url_linkedin        = req["url_linkedin"]
                if "dashboard_config" in req:
                    reg.dashboard_config = req["dashboard_config"]
                if "flimv_model" in req:
                    reg.flimv_model = req["flimv_model"]
                if "max_upload_files" in req:
                    reg.max_upload_files = req["max_upload_files"]
                if "max_upload_images" in req:
                    reg.max_upload_images = req["max_upload_images"]
                if "use_url_images" in req:
                    reg.use_url_images = req["use_url_images"]
                if "track_orders" in req:
                    reg.track_orders = req["track_orders"]
                db.session.commit()
                return True
            return False 
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    # @ns_config.response(HTTPStatus.OK,"Exclui os dados de uma cidade")
    # @ns_config.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    # @auth.login_required
    # def delete(self,id:int):
    #     try:
    #         reg = SysConfig.query.get(id)
    #         setattr(reg,"trash",True)
    #         db.session.commit()
    #         return True
    #     except exc.SQLAlchemyError as e:
    #         return {
    #             "error_code": e.code,
    #             "error_details": e._message(),
    #             "error_sql": e._sql_message()
    #         }