from auth import auth
from os import environ
from flask import request
from http import HTTPStatus
from datetime import datetime
from sqlalchemy import Select, exc, asc, desc, text
from flask_restx import Resource, Namespace, fields
from models.helpers import db, _get_params, Database
from models.public import SysCustomer, SysCustomerPlan, SysCustomerUser, SysUsers

ns_customer = Namespace("customer",description="Operações para manipular dados de clientes")

cust_pag_model = ns_customer.model(
    "Pagination",{
        "registers": fields.Integer,
        "page": fields.Integer,
        "per_page": fields.Integer,
        "pages": fields.Integer,
        "has_next": fields.Integer
    }
)

plan_model = ns_customer.model(
    "Plan",{
        "active": fields.Boolean,
        "activation_date": fields.Date,
        "inactivation_date": fields.Date,
        "payment_method": fields.String,
        "payment_model": fields.String
    }
)

customer_model = ns_customer.model(
    "Customer",{
        "id": fields.Integer,
        "name": fields.String,
        "taxvat": fields.String,
        "postal_code": fields.String,
        "date_created": fields.DateTime,
        "date_updated": fields.DateTime,
        "plan": fields.Nested(plan_model),
    }
)

customer_return = ns_customer.model(
    "CustomerReturn",{
        "pagination": fields.Nested(cust_pag_model),
        "data": fields.List(fields.Nested(customer_model))
    }
)

def _register_customer(
        name:str,
        taxvat:str,
        postal_code:str,
        id_plan:int,
        payment_model:str="M",
        payment_method:str="C",
        users:list|None=None):
    """
    Registra um novo cliente no sistema
    :param name: Nome do cliente
    :param taxvat: CNPJ do cliente
    :param postal_code: CEP do cliente
    :param payment_model: Modelo de pagamento (M = Mensal, Y = Anual)
    :param payment_method: Método de pagamento (C = Cartão de Crédito, P = Pix, B = Boleto)
    """
    try:
        customer:SysCustomer = SysCustomer()
        setattr(customer,"name",name)
        setattr(customer,"taxvat",taxvat)
        setattr(customer,"postal_code",postal_code)
        setattr(customer,"date_created",datetime.now())
        db.session.add(customer)
        db.session.commit()

        if customer.id is not None:
            customer_plan:SysCustomerPlan = SysCustomerPlan()
            customer_plan.id_customer = customer.id
            setattr(customer_plan,"id_plan",id_plan)
            setattr(customer_plan,"activate",True)
            setattr(customer_plan,"activation_date",datetime.now())
            setattr(customer_plan,"payment_model",payment_model)
            setattr(customer_plan,"payment_method",payment_method)
            db.session.add(customer_plan)
            db.session.commit()

            # cria o schema do novo cliente
            tenant = Database(str(customer.id))
            tenant.create_tenant_schema()

            start_date = str(datetime.now().year)+"-01-01"
            end_date   = str(datetime.now().year+50)+"-12-31" # correcao na data final para o fim do ano

            # as funcoes do PostgreSQL sao chamadas com o SELECT
            db.session.execute(text("SELECT public.populate('"+str(customer.id)+"','"+start_date+"','"+end_date+"')"))
            db.session.commit()            
            
        return True
    except exc.SQLAlchemyError as e:
        return {
            "error_code": e.code,
            "error_details": e._message(),
            "error_sql": e._sql_message()
        }, HTTPStatus.BAD_REQUEST


@ns_customer.route("/")
class CustomerList(Resource):
    @ns_customer.response(HTTPStatus.OK,"Obtem um registro de um cliente",customer_return)
    @ns_customer.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_customer.param("page","Número da página de registros","query",type=int,required=True)
    @ns_customer.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_customer.param("query","Texto para busca","query")
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
                trash     = False if not hasattr(params,'trash') else True
                list_all  = False if not hasattr(params,'list_all') else True

            rquery = Select(SysCustomer.id,
                            SysCustomer.name,
                            SysCustomer.taxvat,
                            SysCustomer.date_created,
                            SysCustomer.date_updated,
                            SysCustomerPlan.activate,
                            SysCustomerPlan.activation_date,
                            SysCustomerPlan.inactivation_date,
                            SysCustomerPlan.payment_method,
                            SysCustomerPlan.payment_model)\
                            .join(SysCustomerPlan,SysCustomerPlan.id_customer==SysCustomer.id)\
                            .where(SysCustomer.churn==trash)\
                            .order_by(direction(getattr(SysCustomer,order_by)))
            
            if search is not None:
                rquery = rquery.where(SysCustomer.name.like("%{}%".format(search)))

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
                        "taxvat": m.taxvat,
                        "plan": {
                            "active": m.active,
                            "activation_date": m.activation_date.strftime("%Y-%m-%d") if m.activation_date is not None else None,
                            "inactivation_date": m.inactivation_date.strftime("%Y-%m-%d") if m.inactivation_date is not None else None,
                            "payment_method": m.payment_method,
                            "payment_model": m.payment_model
                        },
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
                }
            else:
                retorno = [{
                        "id":m.id,
                        "name":m.name,
                        "taxvat": m.taxvat,
                        "plan":{
                            "active": m.active,
                            "activation_date": m.activation_date.strftime("%Y-%m-%d") if m.activation_date is not None else None,
                            "inactivation_date": m.inactivation_date.strftime("%Y-%m-%d") if m.inactivation_date is not None else None,
                            "payment_method": m.payment_method,
                            "payment_model": m.payment_model,
                        },
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

    @ns_customer.response(HTTPStatus.OK,"Cria uma novo cliente")
    @ns_customer.response(HTTPStatus.BAD_REQUEST,"Falha ao criar registro!")
    @ns_customer.doc(body=customer_model)
    @auth.login_required
    def post(self):
        req = request.get_json()

        return  _register_customer(
            req["name"],
            req["taxvat"],
            req["postal_code"],
            req["plan"]["id"],
            req["payment_model"] if "payment_model" in req else environ.getenv("F2B_DEFAULT_PAYMENT_MODEL"),
            req["payment_method"] if "payment_method" in req else environ.getenv("F2B_DEFAULT_PAYMENT_METHOD")
        )
        
        
    @ns_customer.response(HTTPStatus.OK,"Exclui os dados de uma ou mais marcas")
    @ns_customer.response(HTTPStatus.BAD_REQUEST,"Falha ao excluir registro!")
    @auth.login_required
    def delete(self)->bool|dict:
        try:
            req = request.get_json()
            for id in req["ids"]:
                brand:SysCustomer|None = SysCustomer.query.get(id)
                setattr(brand,"trash",req["toTrash"])
                db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }


@ns_customer.route("/<int:id>")
@ns_customer.param("id","Id do registro")
class CustomerApi(Resource):
    @ns_customer.response(HTTPStatus.OK,"Retorna os dados dados de um cliente")
    @ns_customer.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def get(self,id:int):
        try:
            cquery:SysCustomer|None = SysCustomer.query.get(id)
            if cquery is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST

            squery:SysCustomerPlan|None = SysCustomerPlan.query.filter(SysCustomerPlan.id_customer==cquery.id).first()
            uquery = db.session.execute(
                Select(SysUsers.name,SysUsers.id,SysUsers.username, SysUsers.type)\
                .join(SysCustomerUser,SysCustomerUser.id_user==SysUsers.id)\
                .where(SysCustomerUser.id_customer==cquery.id)
                ).all()
            return {
                "id": cquery.id,
                "name": cquery.name,
                "taxvat": cquery.taxvat,
                "postal_code": cquery.postal_code,
                "date_created": cquery.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                "date_updated": cquery.date_updated.strftime("%Y-%m-%d %H:%M:%S") if cquery.date_updated is not None else None,
                "plan": {
                    "active": False if squery is None else squery.activate,
                    "activation_date": None if squery is None else (None if squery.activation_date is None else squery.activation_date.strftime("%Y-%m-%d")),
                    "inactivation_date": None if squery is None else (None if squery.inactivation_date is None else squery.inactivation_date.strftime("%Y-%m-%d")),
                    "payment_method": None if squery is None else squery.payment_method,
                    "payment_model": None if squery is None else squery.payment_model
                },
                "users":[{
                    "id": u.id,
                    "name": u.name,
                    "username": u.username,
                    "type": u.type
                }for u in uquery]
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_customer.response(HTTPStatus.OK,"Atualiza os dados de um cliente")
    @ns_customer.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_customer.doc(body=customer_model)
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()
            customer:SysCustomer|None = SysCustomer.query.get(id)
            if customer is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST
            
            customer.name = req["name"]
            customer.taxvat = req["taxvat"]
            customer.postal_code = req["postal_code"]
            setattr(customer,"date_updated",datetime.now())
            db.session.commit()

            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
@ns_customer.route("/<int:id>")
@ns_customer.param("id","Id do registro")
class CustomerPlanApi(Resource):
    @ns_customer.response(HTTPStatus.OK,"Ativa ou Inativa o plano de um cliente")
    @ns_customer.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()
            for id in req["ids"]:
                cst:SysCustomerPlan|None = SysCustomerPlan.query.filter(SysCustomerPlan.id_customer==id).first()
                setattr(cst,"active",req["toActivate"])
                if req["toActivate"]:
                    setattr(cst,"activation_date",datetime.now())
                    setattr(cst,"inactivation_date",None)
                else:
                    setattr(cst,"inactivation_date",datetime.now())
                    setattr(cst,"activation_date",None)
                db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_customer.add_resource(CustomerPlanApi,"/status-plan/<int:id>")


class CustomerSysApi(Resource):
    @ns_customer.response(HTTPStatus.OK,"Registra um novo cliente")
    @ns_customer.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_customer.doc(body=customer_model)
    def post(self):
        
        req = request.get_json()

        return _register_customer(
            req["name"],
            req["taxvat"],
            req["postal_code"],
            req["plan"]["id"],
            req["payment_model"] if "payment_model" in req else "M",
            req["payment_method"] if "payment_method" in req else "C",
            users=req["users"] if "users" in req else None
        )
ns_customer.add_resource(CustomerSysApi,"/register")