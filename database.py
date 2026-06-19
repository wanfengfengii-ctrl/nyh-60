from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "well_efficiency.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from models import (
        Well, WellConfig, Experiment, TimePoint,
        ConfigChangeLog, ExperimentReview, ImportExportLog, ExperimentReport,
        LaborExperiment, LaborTimePoint, LaborAnalysisResult,
        LaborComparisonGroup, LaborComparisonItem,
        SceneConfig, LaborScheme, SceneSimulation, SimulationTimePoint,
        OptimizationReport, OptimizationReportItem,
        HydroExperiment, HydroExperimentDataPoint, HydroAnalysisResult,
        HydroComparisonPeriod, HydroResearchReport
    )
    Base.metadata.create_all(bind=engine)

    try:
        from sqlalchemy import text, inspect
        inspector = inspect(engine)

        with engine.connect() as conn:
            if 'well_config' in inspector.get_table_names():
                cols = [c['name'] for c in inspector.get_columns('well_config')]
                if 'version' not in cols:
                    conn.execute(text("ALTER TABLE well_config ADD COLUMN version INTEGER DEFAULT 1"))
                if 'change_note' not in cols:
                    conn.execute(text("ALTER TABLE well_config ADD COLUMN change_note VARCHAR(500) DEFAULT ''"))
            if 'well' in inspector.get_table_names():
                cols = [c['name'] for c in inspector.get_columns('well')]
                if 'updated_at' not in cols:
                    conn.execute(text("ALTER TABLE well ADD COLUMN updated_at DATETIME"))
            if 'experiment' in inspector.get_table_names():
                cols = [c['name'] for c in inspector.get_columns('experiment')]
                if 'notes' not in cols:
                    conn.execute(text("ALTER TABLE experiment ADD COLUMN notes VARCHAR(1000) DEFAULT ''"))
                if 'reviewer' not in cols:
                    conn.execute(text("ALTER TABLE experiment ADD COLUMN reviewer VARCHAR(100) DEFAULT ''"))
                if 'reviewed_at' not in cols:
                    conn.execute(text("ALTER TABLE experiment ADD COLUMN reviewed_at DATETIME"))
                if 'updated_at' not in cols:
                    conn.execute(text("ALTER TABLE experiment ADD COLUMN updated_at DATETIME"))
            conn.commit()
    except Exception:
        pass
