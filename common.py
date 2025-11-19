import os
import jinja2
import pdfkit
import logging
import requests
from os import environ
from flask import request
from random import seed,randint
from models.public import SysUsers
from models.helpers import Database
from f2bconfig import EntityAction, MailTemplates, DashboardImage, DashboardImageColor

def _before_execute(check:bool = False):
    # apenas no common serah verificada a existencia do auth
    if not check:
        if "Authorization" in request.headers:
            tkn = request.headers["Authorization"].replace("Bearer ","")
            if tkn is not None:
                token = SysUsers.extract_token(tkn) if tkn else None
                tenant = Database(str('public' if token is None else token["profile"]))
                tenant.switch_schema()
    else:
        # se a URL for de autenticacao, configuracao ou do start utilizar o schema public, caso contrario deverah mudar
        # para o schema do cliente
        has_auth = request.base_url.find("users/auth")
        has_config = request.base_url.find("config")
        has_start = request.base_url.find("start")
        
        if has_auth==-1 and has_config==-1 and has_start==-1:
            if "Authorization" in request.headers:
                tkn = request.headers["Authorization"].replace("Bearer ","")
                if tkn is not None:
                    token = SysUsers.extract_token(tkn) if tkn else None
                    tenant = Database(str('' if token is None else token["profile"]))
                    tenant.switch_schema()

def _extract_token(tkn):
    return SysUsers.extract_token(tkn)

def _get_dashboard_config(_config:str):
    if _config=="M":
        return (DashboardImage.MEN.value,DashboardImageColor.MEN.value)
    elif _config=="W":
        return (DashboardImage.WOMEN.value, DashboardImageColor.WOMEN.value)
    elif _config=="H":
        return (DashboardImage.WHEAT.value, DashboardImageColor.WHEAT.value)
    elif _config=="D":
        return (DashboardImage.DRINK.value, DashboardImageColor.DRINK.value)
    elif _config=="S":
        return (DashboardImage.SHOES.value, DashboardImageColor.SHOES.value)
    elif _config=="P":
        return (DashboardImage.PISTON.value, DashboardImageColor.PISTON.value)
    return (DashboardImage.PHARMA.value, DashboardImageColor.PHARMA.value)

def _gen_report(fileName:str,_content:dict):
    try:
        tplLoader  = jinja2.FileSystemLoader(searchpath=str(environ.get("F2B_APP_PATH"))+'assets/layout/')
        tplEnv     = jinja2.Environment(loader=tplLoader)

        bodyReport = tplEnv.get_template(fileName)

        # arquivo header padrao
        headerFile   = "pdf_f2b_header.html"
        headerReport = tplEnv.get_template(headerFile)

        # arquivo footer padrao
        footerFile   = "pdf_f2b_footer.html"
        footerReport = tplEnv.get_template(footerFile)

        #*****************************************************#
        #               MONTAGEM DO HEADER                    #
        #-----------------------------------------------------#
        #conteudo do header padrao
        header_txt = headerReport.render(title=_content["title"])
        seed(1)
        report_id = randint(0,100000)

        header_temp = str(environ.get("F2B_APP_PATH"))+'assets/layout/pdf_header_tmp_'+str(report_id)+'.html'
        footer_temp = str(environ.get("F2B_APP_PATH"))+'assets/layout/pdf_footer_tmp_'+str(report_id)+'.html'

        with open(header_temp,"w") as file_header:
            file_header.write(header_txt)
            file_header.close()
        #-----------------------------------------------------#
        #            FIM DA MONTAGEM DO HEADER                #
        #*****************************************************#


        #*****************************************************#
        #               MONTAGEM DO FOOTER                    #
        #-----------------------------------------------------#
        footer_txt = footerReport.render(footer=_content["footer"])

        with open(footer_temp,"w") as file_footer:
            file_footer.write(footer_txt)
            file_footer.close()
        #-----------------------------------------------------#
        #            FIM DA MONTAGEM DO FOOTER                #
        #*****************************************************#

        body_txt = bodyReport.render(body=_content["body"],regs=len(_content["body"]))
        
        pdfkit.from_string(body_txt,str(environ.get("F2B_APP_PATH"))+'assets/pdf/'+fileName.replace(".html","")+'.pdf',options={
            'encoding': "UTF-8",
            'disable-smart-shrinking':'',
            'header-spacing':3,
            'margin-right': '5mm',
            'margin-left': '5mm',
            'header-html': header_temp,
            'footer-html': footer_temp
        })
        
        if os.path.exists(header_temp):
            os.remove(header_temp)

        if os.path.exists(footer_temp):
            os.remove(footer_temp)

        return True
    except Exception as e:
        logging.error(e)
        return False

def _send_email(p_to:list,p_cc:list,p_subject:str,p_content:str,p_tpl:MailTemplates,p_attach:list|None=None)->bool:
    try:
        tplLoader     = jinja2.FileSystemLoader(searchpath=str(environ.get("F2B_APP_PATH"))+'assets/layout/')
        tplEnv        = jinja2.Environment(loader=tplLoader)
        layoutFile    = p_tpl.value
        mailTemplate  = tplEnv.get_template(layoutFile)
        mail_template = mailTemplate.render(
            content=p_content,
            url=(str(environ.get("F2B_APP_URL"))) +('reset-password/' if p_tpl==MailTemplates.PWD_RECOVERY else "")
        )

        if p_attach is not None:
            json_content= {
                "sender": {
                    "name": str(environ.get("F2B_EMAIL_FROM_NAME")),
                    "email": str(environ.get("F2B_EMAIL_FROM_VALUE"))
                },
                "to": [{
                    "email": one_to.split()
                }for one_to in p_to],
                "cc": [{
                    "email": str(one_cc).split()
                }for one_cc in p_cc],
                "htmlContent": mail_template,
                "subject": p_subject,
                "attachment": [
                    {
                        "content": att['content'],
                        "name": att['filename']
                    }for att in p_attach]
            }
        else:
            json_content= {
                "sender": {
                    "name": str(environ.get("F2B_EMAIL_FROM_NAME")),
                    "email": str(environ.get("F2B_EMAIL_FROM_VALUE"))
                },
                "to": [{
                    "email": one_to.split()
                }for one_to in p_to],
                "cc": [{
                    "email": str(one_cc).split()
                }for one_cc in p_cc],
                "htmlContent": mail_template,
                "subject": p_subject,
            }
        resp = requests.post("https://api.brevo.com/v3/smtp/email",json=json_content,headers={
            'accept':'application/json',
            'content-type': 'application/json',
            'api-key': str(environ.get("F2B_BREVO_API_KEY"))
        })
        if resp.status_code==200:
            return True
        return False
    except Exception as e:
        logging.error(e)
        return False
    
def _format_action(act:EntityAction) ->str:
    if act==EntityAction.DATA_REGISTERED.value:
        return "Registro de Dados"
    if act==EntityAction.DATA_UPDATED.value:
        return "Atualização de Dados"
    if act==EntityAction.DATA_DELETED.value:
        return "Arquivamento de Dados"
    if act==EntityAction.MOVE_CRM_FUNNEL.value:
        return "Movimento de Funil/Estágio"
    if act==EntityAction.CHAT_MESSAGE_SEND.value:
        return "Envio de mensagem"
    if act==EntityAction.CHAT_MESSAGE_RECEIVED.value:
        return "Recebimento de mensagem"
    if act==EntityAction.ORDER_CREATED.value:
        return "Pedido criado"
    if act==EntityAction.ORDER_UPDATED.value:
        return "Pedido atualizado"
    if act==EntityAction.ORDER_DELETED.value:
        return "Pedido arquivado"
    if act==EntityAction.TASK_CREATED.value:
        return "Tarefa criada"
    if act==EntityAction.FILE_ATTACHED.value:
        return "Arquivo anexado"
    if act==EntityAction.FILE_DETTACHED.value:
        return "Arquivo excluído"
    if act==EntityAction.EMAIL_SENDED.value:
        return "E-mail enviado"
    if act==EntityAction.EMAIL_REPLIED.value:
        return "E-mail respondido"
    if act==EntityAction.RETURN_CREATED.value:
        return "Devolução criada"
    if act==EntityAction.RETURN_UPDATED.value:
        return "Devolução atualizada"
    if act==EntityAction.FINANCIAL_BLOQUED.value:
        return "Bloqueio financeiro"
    if act==EntityAction.FINANCIAL_UNBLOQUED.value:
        return "Desbloqueio financeiro"
    if act==EntityAction.COMMENT_ADDED.value:
        return "Observação"
    return ""