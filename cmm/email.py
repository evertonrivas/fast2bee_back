import os
import base64
import mimetypes
from auth import auth
from flask import request
from http import HTTPStatus
from common import _send_email
from werkzeug import exceptions
from f2bconfig import MailTemplates
from flask_restx import Resource,Namespace
from sqlalchemy import Select
from models.helpers import db
from models.public import SysConfig

ns_email = Namespace("email",description="Operações para manipular upload de dados")

@ns_email.route("/")
class EmailApi(Resource):

    @ns_email.response(HTTPStatus.OK,"Realiza envio de arquivo(s) para o servidor")
    @ns_email.response(HTTPStatus.BAD_REQUEST,"Falha ao enviar arquivo(s)!")
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()
            attachs = []

            # get brevo API Key
            brevo_key = db.session.execute(Select(SysConfig.email_brevo_api_key).where(SysConfig.id_customer==str(request.headers.get("x-customer")))).first()
            if brevo_key is None:
                return False

            #verifica se os arquivos existem
            fpath = str(os.environ.get("F2B_APP_PATH"))+'assets/tmp/'
            for file in req['attachments']:
                if not os.path.exists(fpath+file):
                    pass
                else:
                    with open(fpath+file,"rb") as f:
                        content = base64.b64encode(f.read())
                    attachs.append({
                        "name": file,
                        "type": mimetypes.guess_type(fpath+file),
                        "content": content
                    })
            if _send_email(
                req['to'],
                [],
                req['subject'],
                req['content'],
                MailTemplates.DEFAULT,
                brevo_key.email_brevo_api_key,
                attachs) is True:
                #limpa os arquivos do tmp
                for file in req["attachments"]:
                    os.remove(fpath+file)
                return True
            return False
        except exceptions.HTTPException as e:
            return {
                "error_code": e.code,
                "error_details": e.description,
                "error_sql": ''
            }