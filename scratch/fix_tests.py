import glob
import uuid

for f in glob.glob('backend/tests/test_artifact_*.py'):
    with open(f, 'r') as file:
        content = file.read()
    
    if "from sqlalchemy.pool import StaticPool" not in content:
        content = content.replace(
            'from sqlalchemy import create_engine',
            'from sqlalchemy import create_engine\nfrom sqlalchemy.pool import StaticPool'
        )
    
    content = content.replace(
        'create_engine("sqlite:///:memory:")',
        'create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)'
    )
    
    with open(f, 'w') as file:
        file.write(content)
