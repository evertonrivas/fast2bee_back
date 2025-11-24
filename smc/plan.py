import simplejson
from auth import auth
from os import environ
from flask import request
from decimal import Decimal
from http import HTTPStatus
from datetime import datetime
from models.public import SysCustomerPlan, SysPlan
from models.helpers import _get_params, db
from sqlalchemy import Select, exc, asc, desc
from flask_restx import Resource, Namespace, fields

ns_plan = Namespace("plan",description="Operações para manipular dados de planos de assinatura")

plan_pag_model = ns_plan.model(
    "Pagination",{
        "registers": fields.Integer,
        "page": fields.Integer,
        "per_page": fields.Integer,
        "pages": fields.Integer,
        "has_next": fields.Integer
    }
)

plan_model = ns_plan.model(
    "Plan",{
        "id": fields.Integer,
        "name": fields.String,
        "plan_value": fields.Float,
        "plan_adm_licenses": fields.Integer,
        "plan_user_licenses": fields.Integer,
        "plan_repr_licenses": fields.Integer,
        "plan_store_licenses": fields.Integer,
        "plan_istore_licenses": fields.Integer,
        "date_created": fields.DateTime,
        "date_updated": fields.DateTime
    }
)

plan_return = ns_plan.model(
    "PlanReturn",{
        "pagination": fields.Nested(plan_pag_model),
        "data": fields.List(fields.Nested(plan_model))
    }
)


@ns_plan.route("/")
class PaymentList(Resource):
    @ns_plan.response(HTTPStatus.OK,"Obtem um registro de um plano",plan_return)
    @ns_plan.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_plan.param("page","Número da página de registros","query",type=int,required=True)
    @ns_plan.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_plan.param("query","Texto para busca","query")
    @auth.login_required
    def get(self):
        pag_num  = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size = int(str(environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        query    = "" if request.args.get("query") is None else str(request.args.get("query"))

        try:
            params    = _get_params(query)
            if params is not None:
                direction = asc if not hasattr(params,'order') else asc if str(params.order).upper()=='ASC' else desc
                order_by  = 'id' if not hasattr(params,'order_by') else params.order_by
                search    = None if not hasattr(params,"search") else params.search
                list_all  = False if not hasattr(params,'list_all') else True

            rquery = Select(SysPlan.id,
                            SysPlan.name,
                            SysPlan.date_created,
                            SysPlan.date_updated,
                            SysPlan.value,
                            SysPlan.adm_licenses,
                            SysPlan.user_licenses,
                            SysPlan.repr_licenses,
                            SysPlan.store_licenses,
                            SysPlan.istore_licenses)\
                            .order_by(direction(getattr(SysPlan,order_by)))
            
            if search is not None:
                rquery = rquery.where(SysPlan.name.like("%{}%".format(search)))

            if not list_all:
                pag = db.paginate(rquery,page=pag_num,per_page=pag_size)
                rquery = rquery.limit(pag_size).offset((pag_num - 1) * pag_size)

                retorno = {
                    "pagination":{
                        "registers": pag.total,
                        "page": pag_num,
                        "per_page": pag_size,
                        "pages": pag.pages,
                        "has_next": pag.has_next
                    },
                    "data":[{
                        "id": m.id,
                        "name": m.name,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
                }
            else:
                retorno = [{
                        "id":m.id,
                        "name":m.name,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
            return retorno
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_plan.response(HTTPStatus.OK,"Cria uma nova marca")
    @ns_plan.response(HTTPStatus.BAD_REQUEST,"Falha ao criar registro!")
    @ns_plan.doc(body=plan_model)
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()

            plan:SysPlan = SysPlan()
            plan.name = req["name"]
            plan.value = req["value"]
            plan.adm_licenses = req["adm_licenses"]
            plan.user_licenses = req["user_licenses"]
            plan.repr_licenses = req["repr_licenses"]
            plan.store_licenses = req["store_licenses"]
            plan.istore_licenses = req["istore_licenses"]
            setattr(plan,"date_created",datetime.now())
            db.session.add(plan)
            db.session.commit()

            return plan.id
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
        
    @ns_plan.response(HTTPStatus.OK,"Exclui os dados de uma ou mais marcas")
    @ns_plan.response(HTTPStatus.BAD_REQUEST,"Falha ao excluir registro!")
    @auth.login_required
    def delete(self)->bool|dict:
        try:
            req = request.get_json()
            for id in req["ids"]:
                plan:SysPlan = SysPlan.query.get(id) # type: ignore
                setattr(plan,"trash",req["toTrash"])
                db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

@ns_plan.route("/<int:id>")
@ns_plan.param("id","Id do registro")
class PaymentApi(Resource):
    @ns_plan.response(HTTPStatus.OK,"Retorna os dados dados de uma marca")
    @ns_plan.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def get(self,id:int):
        try:
            cquery = SysPlan.query.get(id)
            if cquery is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST

            return {
                "id": cquery.id,
                "name": cquery.name,
                "value": cquery.value,
                "adm_licenses": cquery.adm_licenses,
                "user_licenses": cquery.user_licenses,
                "repr_licenses": cquery.repr_licenses,
                "store_licenses": cquery.store_licenses,
                "istore_licenses": cquery.istore_licenses,
                "date_created": cquery.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                "date_updated": cquery.date_updated.strftime("%Y-%m-%d %H:%M:%S") if cquery.date_updated is not None else None
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_plan.response(HTTPStatus.OK,"Atualiza os dados de uma marca")
    @ns_plan.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_plan.doc(body=plan_model)
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()
            plan:SysPlan|None = SysPlan.query.get(id)
            if plan is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST
            
            plan.name  = req["name"]
            plan.value = req["value"]
            plan.adm_licenses = req["adm_licenses"]
            plan.user_licenses = req["user_licenses"]
            plan.repr_licenses = req["repr_licenses"]
            plan.store_licenses = req["store_licenses"]
            plan.istore_licenses = req["istore_licenses"]
            setattr(plan,"date_updated",datetime.now())
            db.session.commit()

            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        

class CustomerPlan(Resource):
    @ns_plan.response(HTTPStatus.OK,"Retorna o total de Usuarios por tipo")
    @ns_plan.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def get(self):
        try:
            stmt = Select(
                SysPlan.name,
                SysPlan.adm_licenses,
                SysPlan.repr_licenses,
                SysPlan.store_licenses,
                SysPlan.istore_licenses,
                SysPlan.user_licenses,
                SysPlan.value).join(SysCustomerPlan,SysCustomerPlan.id_plan==SysPlan.id)\
                .where(SysCustomerPlan.id_customer==request.headers.get("x-customer",None))
            row = db.session.execute(stmt).first()
            if row is None: 
                return{
                    "error_code": HTTPStatus.BAD_REQUEST,
                    "error_details": "Plano não encontrado!",
                    "error_sql": ""
                },HTTPStatus.BAD_REQUEST
            else:
                return{
                    "name": row.name,
                    "adm_licenses": row.adm_licenses,
                    "repr_licenses": row.repr_licenses,
                    "store_licenses": row.store_licenses,
                    "istore_licenses": row.istore_licenses,
                    "user_licenses": row.user_licenses,
                    "value": simplejson.dumps(Decimal(row.value))
                }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
 
ns_plan.add_resource(CustomerPlan,'/my-plan/')