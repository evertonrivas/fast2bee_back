import locale
from flask import Flask
from cmm.api import bp_cmm
from crm.api import bp_crm
from b2b.api import bp_b2b
from fpr.api import bp_fpr
from scm.api import bp_scm
from mpg.api import bp_mpg
from smc.api import bp_smc
from sqlalchemy import text
from flask_cors import CORS
from os import environ, path
from sqlalchemy import Select
from dotenv import load_dotenv
from models.public import SysCustomer
from models.helpers import db, migrate

BASEDIR = path.abspath(path.dirname(__file__))
load_dotenv(path.join(BASEDIR, '.env'))

# locale.setlocale(locale.LC_TIME,str(environ.get("F2B_LOCALE")))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = str(environ.get("F2B_DB_LIB"))+"://"+str(environ.get("F2B_DB_USER"))+":"+\
str(environ.get("F2B_DB_PASS"))+"@"+str(environ.get("F2B_DB_HOST"))+"/"+str(environ.get("F2B_DB_NAME"))
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True
}
app.config['SQLALCHEMY_BINDS'] = {
    "public": app.config["SQLALCHEMY_DATABASE_URI"]
}

db.init_app(app)
try:
    with app.app_context():
        #valida a conexao com o banco de daods
        with db.engine.begin() as conn:
            conn.execute(text("SELECT 1"))
            conn.close()

        # #se nao existirem as tabelas tenta cria-las
        # db.create_all("public")

        # # atualiza os tenants
        # tenants = db.session.execute(Select(SysCustomer.id)).all()
        # for tenant in tenants:
        #     schema = str(tenant.id)
        #     db.session.execute(text(f'set search_path to "{schema}"'))
        #     db.session.commit()
        #     db.metadata.create_all(
        #         db.engine.execution_options(
        #             schema_translate_map={None:schema}
        #         )
        #     )

except Exception as e:
    print(e)
    print("###################################################")
    print("Por favor, inicialize a instância do Banco de Dados")
    print("###################################################")
    quit()

migrate.init_app(app, db)

app.register_blueprint(bp_cmm)
app.register_blueprint(bp_crm)
app.register_blueprint(bp_b2b)
app.register_blueprint(bp_fpr)
app.register_blueprint(bp_scm)
app.register_blueprint(bp_mpg)
app.register_blueprint(bp_smc)

CORS(app, resources={r"/*": {"origins": "*"}},supports_credentials=True)
# CORS(app, resources={r"/*": {"origins": "https://system.fast2bee.com"}},supports_credentials=True)

@app.route("/")
def index():
    return """<html>
        <head>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-GLhlTQ8iRABdZLl6O3oVMWSktQOp6b7In1Zl3/Jr59b6EGGoI1aFkw7cmDA6j6gD" crossorigin="anonymous">
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js" integrity="sha384-w76AqPfDkMBDXo30jS1Sgez6pr3x5MlQ1ZAGC+nuZB+EYdgRZgiwxhTBTkF7CXvN" crossorigin="anonymous"></script>
        </head>
        <body>
        <div class='container'>
            <div class='row'><div class='col'>&nbsp;</div></div>
            <div class='row'><div class='col'>&nbsp;</div></div>
            <div class='row'><div class='col'>&nbsp;</div></div>
            <div class='row'>
                <div class='col-2'>&nbsp;</div>
                <div class='col'>
                    <div class='card border border-info'>
                        <div class='card-header text-center fw-bold'>Fast2Bee - API</div>
                        <div class='card-body'>
                            <p class='card-text'>
                            O sistema Fast2Bee possui 6 m&oacute;dulos, cada um com seu backend em REST API com sua respectiva documenta&ccedil;&atilde;o.
                            Para acessar as documenta&ccedil;&otilde;es das APIS, clique nos links abaixo:<br/><br/>
                            F2B_B2B - Business to Business <a href='/b2b/api'>/b2b/api</a><br>
                            F2B_FPR - Finished Product Return <a href='/fpr/api'>/fpr/api</a><br>
                            <!-- F2B_POS - Point Of Sale <a href='/pos/api'>/pos/api</a><br> -->
                            F2B_CRM - Customer Relashionship Management <a href='/crm/api'>/crm/api</a><br>
                            F2B_SCM - Sales Calendar Management <a href='/scm/api'>/scm/api</a><br>
                            F2B_MPG - Marketing Plan Generator <a href='/mpg/api'>/mpg/api</a><br><hr size='1'>

                            F2B_CMM - M&oacute;dulo Common (Fun&ccedil;&otilde;es comuns dos m&oacute;dulos) <a href='/cmm/api'>/cmm/api</a><br>
                            F2B_SMC - System Management Customer (Módulo de Gestão dos Clientes e assinaturas) <a href='/smc/api'>/smc/api</a>
                            </p>
                        </div>
                    </div>
                </div>
                <div class='col-2'>&nbsp;</div>
            </div>
        </div>
        </body>
        </html>
    """

if __name__=="__main__":
    app.run(port=5000,debug=True,host="0.0.0.0")