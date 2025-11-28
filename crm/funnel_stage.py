from auth import auth
from os import environ
from flask import request
from http import HTTPStatus
from models.helpers import _get_params, db
from flask_restx import Resource, Namespace
from sqlalchemy import Select, Update, desc, exc, and_, asc, or_
from models.tenant import CrmFunnelStageCustomer, CrmFunnelStage
from f2bconfig import CrmFunnelType, EntityAction, LegalEntityType
from models.tenant import CmmLegalEntities, CrmFunnel, _save_entity_log


ns_fun_stg = Namespace("funnel-stages",description="Operações para manipular estágios dos funis de clientes")

@ns_fun_stg.route("/")
class FunnelStagesApi(Resource):
    @ns_fun_stg.response(HTTPStatus.OK,"Exibe os dados de um estágio de um funil")
    @ns_fun_stg.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_fun_stg.param("page","Número da página de registros","query",type=int,required=True)
    @ns_fun_stg.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_fun_stg.param("query","Texto para busca","query")
    @auth.login_required
    def get(self):
        pag_num  = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size = int(str(environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        query    = "" if request.args.get("query") is None else request.args.get("query")
        try:
            params    = _get_params(query)
            trash     = False if not hasattr(params,'trash') else True
            list_all  = False if not hasattr(params,"list_all") else True
            order_by  = "id" if not hasattr(params,"order_by") else params.order_by if params is not None else 'id'
            direction = asc if not hasattr(params,'order') else asc if params is not None and params.order=='ASC' else desc

            filter_search = None if not hasattr(params,"search") else params.search if params is not None else None
            filter_funnel = None if not hasattr(params,"funnel") else params.funnel if params is not None else None
            sale_funnel   = False if not hasattr(params,"sales") else True

            rquery = Select(CrmFunnelStage.id,
                            CrmFunnelStage.id_funnel,
                            CrmFunnel.name.label("funnel"),
                            CrmFunnelStage.name,
                            CrmFunnelStage.icon,
                            CrmFunnelStage.icon_color,
                            CrmFunnelStage.color,
                            CrmFunnelStage.order,
                            CrmFunnelStage.date_created,
                            CrmFunnelStage.date_updated)\
                            .select_from(CrmFunnel)\
                            .outerjoin(CrmFunnelStage,CrmFunnelStage.id_funnel==CrmFunnel.id)\
                            .where(CrmFunnelStage.trash==trash)\
                            .order_by(direction(getattr(CrmFunnelStage,order_by)))
            
            if filter_search is not None:
                rquery = rquery.where(or_(
                    CrmFunnelStage.name.like("%{}%".format(filter_search)),
                    CrmFunnel.name.like("%{}%".format(filter_search))
                ))

            if filter_funnel is not None:
                rquery = rquery.where(CrmFunnelStage.id_funnel==filter_funnel)

            if sale_funnel is True:
                rquery = rquery.where(CrmFunnel.type==CrmFunnelType.SALES.value)

            if list_all is False:
                pag    = db.paginate(rquery,page=pag_num,per_page=pag_size)
                rquery = rquery.limit(pag_size).offset((pag_num - 1) * pag_size)
                return {
                    "pagination":{
                        "registers": pag.total,
                        "page": pag_num,
                        "per_page": pag_size,
                        "pages": pag.pages,
                        "has_next": pag.has_next
                    },
                    "data":[{
                        "id": m.id,
                        "id_funel":m.id_funnel,
                        "funnel": m.funnel,
                        "name": m.name,
                        "icon": m.icon,
                        "icon_color": m.icon_color,
                        "color": m.color,
                        "order": m.order,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    }for m in db.session.execute(rquery)]
                }
            else:
                return [{
                        "id": m.id,
                        "id_funel":m.id_funnel,
                        "funnel": m.funnel,
                        "name": m.name,
                        "icon": m.icon,
                        "icon_color": m.icon_color,
                        "color": m.color,
                        "order": m.order,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    }for m in db.session.execute(rquery)]
        except exc.SQLAlchemyError as e:
            return{
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()

            color = str(req["hex_color"]).replace("#","")
            c1 = hex(int(color[0:2],16)-101).replace("0x","")
            c2 = hex(int(color[2:4],16)-101).replace("0x","")
            c3 = hex(int(color[4:6],16)-101).replace("0x","")
            icon_color = "#"+c1+c2+c3

            stage = CrmFunnelStage()
            stage.id_funnel  = req["id_funnel"]
            stage.name       = req["name"]
            stage.icon       = req["icon"]
            setattr(stage,"icon_color",icon_color)
            stage.color      = req["hex_color"]
            stage.order      = req["order"]
            db.session.add(stage)
            db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return{
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    @ns_fun_stg.response(HTTPStatus.OK,"Exclui um estágio de um funil")
    @ns_fun_stg.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def delete(self)->bool|dict:
        try:
            req = request.get_json()
            for id in req["ids"]:
                stage = CrmFunnelStage.query.get(id)
                db.session.delete(stage)
                db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_fun_stg.response(HTTPStatus.OK,"Lista os clientes que nao estao em nenhum funil")
    @ns_fun_stg.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def patch(self):
        try:
            stmt = Select(CmmLegalEntities.id,
                          CmmLegalEntities.origin_id,
                          CmmLegalEntities.name,
                          CmmLegalEntities.fantasy_name,
                          CmmLegalEntities.taxvat,
                          CmmLegalEntities.id_city,
                          CmmLegalEntities.postal_code,
                          CmmLegalEntities.neighborhood,
                          CmmLegalEntities.type,
                          CmmLegalEntities.address)\
                .where(and_(
                    CmmLegalEntities.type==LegalEntityType.CUSTOMER.value,
                    CmmLegalEntities.trash.is_(False),
                    CmmLegalEntities.id.not_in(
                        Select(CrmFunnelStageCustomer.id_customer).select_from(CrmFunnelStageCustomer)
                    )
                ))
            return [{
                "id":m.id,
                "origin_id": m.origin_id,
                "name":m.name,
                "fantasy_name":m.fantasy_name,
                "taxvat":m.taxvat,
                "city": {
                    "id": m.id_city,
                    "state_region":{
                        'id':0,
                        "country":{
                            "id":0,
                            "name":""
                        },
                        "name":"",
                        "acronym":""
                    },
                    "name":"",
                    "brazil_ibge_code":None
                },
                "agent": None,
                "contacts": [],
                "web": [],
                "files": [],
                "postal_code":m.postal_code,
                "neighborhood":m.neighborhood,
                "address":m.address,
                "type":m.type
            }for m in db.session.execute(stmt).all()]
        except exc.SQLAlchemyError as e:
            return{
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

@ns_fun_stg.route("/<int:id>")
@ns_fun_stg.param("id","Id do registro")
class FunnelStageApi(Resource):
    @ns_fun_stg.response(HTTPStatus.OK,"Exibe os dados de um estágio de um funil")
    @ns_fun_stg.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def get(self,id:int):
        try:
            reg:CrmFunnelStage|None = CrmFunnelStage.query.get(id)
            if reg is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST
            
            return {
                "id": reg.id,
                "id_funnel": reg.id_funnel,
                "name": reg.name,
                "icon": reg.icon,
                "icon_color": reg.icon_color,
                "color": reg.color,
                "order": reg.order,
                "date_created": reg.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                "date_updated": None if reg.date_updated is None else reg.date_updated.strftime("%Y-%m-%d %H:%M:%S"),
                "trash": reg.trash
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_fun_stg.response(HTTPStatus.OK,"Cria ou atualiza um estágio em um funil")
    @ns_fun_stg.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_fun_stg.param("id_funnel","Id de registro do funil",required=True,type=int)
    @ns_fun_stg.param("name","Nome do estágio do funil",required=True)
    @ns_fun_stg.param("order","Ordem do estágio dentro do funil",type=int,required=True)
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()

            color = str(req["hex_color"]).replace("#","")
            c1 = hex(int(color[0:2],16)-101).replace("0x","")
            c2 = hex(int(color[2:4],16)-101).replace("0x","")
            c3 = hex(int(color[4:6],16)-101).replace("0x","")
            icon_color = "#"+c1+c2+c3

            if id > 0:
                stage:CrmFunnelStage|None = CrmFunnelStage.query.get(id)
                if stage is not None:
                    stage.id_funnel  = req["id_funnel"]
                    stage.name       = req["name"]
                    stage.icon       = req["icon"]
                    setattr(stage,"icon_color",icon_color)
                    stage.color      = req["hex_color"]
                    stage.order      = req["order"]
                    db.session.commit()
                    return stage.id
            else:
                stage = CrmFunnelStage()
                stage.id_funnel  = req["id_funnel"]
                stage.name       = req["name"]
                stage.icon       = req["icon"]
                setattr(stage,"icon_color",icon_color)
                stage.color      = req["hex_color"]
                stage.order      = req["order"]
                db.session.add(stage)
                db.session.commit()
                return stage.id
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
class FunnelStageCustomer(Resource):
    @auth.login_required
    def get(self):
        try:
            id_customer = request.args.get("id_customer")
            new_stage   = request.args.get("id_stage")

            customer_stage = CrmFunnelStageCustomer.query.filter(CrmFunnelStageCustomer.id_customer==id_customer).one()
            customer_stage.id_funnel_stage = new_stage
            stage = db.session.execute(Select(CrmFunnelStage.name).where(CrmFunnelStage.id==new_stage)).first()
            db.session.commit()
            _save_entity_log(int(str(id_customer)),EntityAction.MOVE_CRM_FUNNEL,'Movido para o estágio '+(stage.name if stage is not None else ''))

            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    @ns_fun_stg.response(HTTPStatus.OK,"Move um ou mais clientes para um estagio de um funil")
    @ns_fun_stg.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()
            for customer in req['customers']:
                db.session.execute(
                    Update(CrmFunnelStageCustomer).values(id_funnel_stage=req["stage"]).where(CrmFunnelStageCustomer.id_customer==customer)
                )
                db.session.commit()
                stage = db.session.execute(Select(CrmFunnelStage.name).where(CrmFunnelStage.id==req['stage'])).first()
                _save_entity_log(customer,EntityAction.MOVE_CRM_FUNNEL,'Movido para o estágio '+(stage.name if stage is not None else ''))
                db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    @auth.login_required
    def delete(self):
        try:
            req = request.get_json()
            for customer in req['customers']:
                customer_state = CrmFunnelStageCustomer.query.filter(CrmFunnelStageCustomer.id_customer==customer).one()
                db.session.delete(customer_state)
                db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_fun_stg.add_resource(FunnelStageCustomer,'/move-customer')

class FunnelStageNotification(Resource):
    def get(self):
        try:
            pass
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    def post(self):
        try:
            pass
        except Exception:
            pass

    def delete(self):
        try:
            pass
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

ns_fun_stg.add_resource(FunnelStageCustomer,'/notification')