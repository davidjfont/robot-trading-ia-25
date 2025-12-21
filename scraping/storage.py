"""
Storage - Sistema de almacenamiento SQLite para datos scrapeados y trading
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger
import os
import yaml


Base = declarative_base()


class ScrapedNews(Base):
    """Modelo para noticias scrapeadas"""
    __tablename__ = 'scraped_news'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    url = Column(String(1000))
    scraped_at = Column(DateTime, default=datetime.now)
    sentiment = Column(String(20))  # bullish/bearish/neutral
    sentiment_score = Column(Float)  # -1 a 1
    impact = Column(String(20))  # high/medium/low
    processed = Column(Boolean, default=False)
    extra_data = Column(JSON)


class EconomicEvent(Base):
    """Modelo para eventos del calendario económico"""
    __tablename__ = 'economic_events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    currency = Column(String(10))
    impact = Column(String(20))
    event_time = Column(String(50))
    actual = Column(String(50))
    forecast = Column(String(50))
    previous = Column(String(50))
    scraped_at = Column(DateTime, default=datetime.now)


class TradingSignal(Base):
    """Modelo para señales de trading generadas"""
    __tablename__ = 'trading_signals'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    signal_type = Column(String(20))  # BUY/SELL/HOLD
    strength = Column(Float)  # 0-1
    technical_score = Column(Float)
    sentiment_score = Column(Float)
    news_score = Column(Float)
    combined_score = Column(Float)
    created_at = Column(DateTime, default=datetime.now)
    executed = Column(Boolean, default=False)
    extra_data = Column(JSON)


class TradeHistory(Base):
    """Modelo para historial de operaciones"""
    __tablename__ = 'trade_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket = Column(Integer, unique=True)
    symbol = Column(String(20), nullable=False)
    order_type = Column(String(20))  # BUY/SELL
    volume = Column(Float)
    open_price = Column(Float)
    close_price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    profit = Column(Float)
    opened_at = Column(DateTime)
    closed_at = Column(DateTime)
    status = Column(String(20))  # open/closed/pending
    signal_id = Column(Integer)  # Referencia a la señal que generó la operación
    extra_data = Column(JSON)


class AgentLog(Base):
    """Modelo para logs de agentes"""
    __tablename__ = 'agent_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), nullable=False)
    action = Column(String(100))
    result = Column(Text)
    success = Column(Boolean)
    execution_time_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class Storage:
    """
    Gestor de almacenamiento SQLite para el sistema de trading.
    
    Uso:
        storage = Storage()
        storage.save_news([ScrapedItem(...)])
        news = storage.get_recent_news(hours=24)
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """Inicializa la conexión a SQLite"""
        self.config = self._load_config(config_path)
        
        db_path = self.config.get("database", {}).get("path", "data/trading.db")
        
        # Asegurar que el directorio existe
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_db_path = os.path.join(base_dir, db_path)
        os.makedirs(os.path.dirname(full_db_path), exist_ok=True)
        
        self.engine = create_engine(f"sqlite:///{full_db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        logger.info(f"Storage inicializado: {full_db_path}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carga configuración"""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, config_path)
            
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return {}
    
    def get_session(self) -> Session:
        """Obtiene una nueva sesión"""
        return self.SessionLocal()
    
    # ========== Noticias ==========
    
    def save_news(self, items: List[Any]) -> int:
        """
        Guarda noticias scrapeadas
        
        Args:
            items: Lista de ScrapedItem
        
        Returns:
            Número de items guardados
        """
        session = self.get_session()
        saved = 0
        
        try:
            for item in items:
                # Verificar si ya existe (por URL)
                exists = session.query(ScrapedNews).filter(
                    ScrapedNews.url == item.url
                ).first()
                
                if exists:
                    continue
                
                news = ScrapedNews(
                    source=item.source,
                    title=item.title,
                    content=item.content,
                    url=item.url,
                    scraped_at=item.timestamp,
                    extra_data=item.extra_data
                )
                session.add(news)
                saved += 1
            
            session.commit()
            logger.debug(f"Guardadas {saved} noticias nuevas")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error guardando noticias: {e}")
        finally:
            session.close()
        
        return saved
    
    def get_recent_news(self, hours: int = 24, processed: Optional[bool] = None) -> List[ScrapedNews]:
        """
        Obtiene noticias recientes
        
        Args:
            hours: Horas hacia atrás
            processed: Filtrar por procesado (None = todos)
        """
        session = self.get_session()
        
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            query = session.query(ScrapedNews).filter(
                ScrapedNews.scraped_at >= cutoff
            )
            
            if processed is not None:
                query = query.filter(ScrapedNews.processed == processed)
            
            return query.order_by(ScrapedNews.scraped_at.desc()).all()
            
        finally:
            session.close()
    
    def mark_news_processed(self, news_id: int, sentiment: str, score: float, impact: str):
        """Marca una noticia como procesada con su análisis"""
        session = self.get_session()
        
        try:
            news = session.query(ScrapedNews).filter(ScrapedNews.id == news_id).first()
            if news:
                news.processed = True
                news.sentiment = sentiment
                news.sentiment_score = score
                news.impact = impact
                session.commit()
        finally:
            session.close()
    
    # ========== Eventos Económicos ==========
    
    def save_events(self, items: List[Any]) -> int:
        """Guarda eventos del calendario económico"""
        session = self.get_session()
        saved = 0
        
        try:
            # Limpiar eventos antiguos (más de 7 días)
            cutoff = datetime.now() - timedelta(days=7)
            session.query(EconomicEvent).filter(
                EconomicEvent.scraped_at < cutoff
            ).delete()
            
            for item in items:
                event = EconomicEvent(
                    name=item.title,
                    currency=item.extra_data.get("currency", ""),
                    impact=item.extra_data.get("impact", "low"),
                    event_time=item.extra_data.get("time", ""),
                    actual=item.extra_data.get("actual", ""),
                    forecast=item.extra_data.get("forecast", ""),
                    previous=item.extra_data.get("previous", ""),
                    scraped_at=item.timestamp
                )
                session.add(event)
                saved += 1
            
            session.commit()
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error guardando eventos: {e}")
        finally:
            session.close()
        
        return saved
    
    def get_high_impact_events(self, currency: Optional[str] = None) -> List[EconomicEvent]:
        """Obtiene eventos de alto impacto"""
        session = self.get_session()
        
        try:
            query = session.query(EconomicEvent).filter(
                EconomicEvent.impact == "high"
            )
            
            if currency:
                query = query.filter(EconomicEvent.currency.like(f"%{currency}%"))
            
            return query.all()
            
        finally:
            session.close()
    
    # ========== Señales ==========
    
    def save_signal(self, signal: Dict[str, Any]) -> int:
        """Guarda una señal de trading"""
        session = self.get_session()
        
        try:
            sig = TradingSignal(
                symbol=signal.get("symbol"),
                signal_type=signal.get("type"),
                strength=signal.get("strength"),
                technical_score=signal.get("technical_score"),
                sentiment_score=signal.get("sentiment_score"),
                news_score=signal.get("news_score"),
                combined_score=signal.get("combined_score"),
                extra_data=signal.get("metadata", {})
            )
            session.add(sig)
            session.commit()
            
            return sig.id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error guardando señal: {e}")
            return 0
        finally:
            session.close()
    
    def get_recent_signals(self, symbol: Optional[str] = None, hours: int = 24) -> List[TradingSignal]:
        """Obtiene señales recientes"""
        session = self.get_session()
        
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            query = session.query(TradingSignal).filter(
                TradingSignal.created_at >= cutoff
            )
            
            if symbol:
                query = query.filter(TradingSignal.symbol == symbol)
            
            return query.order_by(TradingSignal.created_at.desc()).all()
            
        finally:
            session.close()
    
    # ========== Historial de Trades ==========
    
    def save_trade(self, trade: Dict[str, Any]) -> int:
        """Guarda una operación"""
        session = self.get_session()
        
        try:
            t = TradeHistory(
                ticket=trade.get("ticket"),
                symbol=trade.get("symbol"),
                order_type=trade.get("type"),
                volume=trade.get("volume"),
                open_price=trade.get("open_price"),
                close_price=trade.get("close_price"),
                sl=trade.get("sl"),
                tp=trade.get("tp"),
                profit=trade.get("profit"),
                opened_at=trade.get("opened_at"),
                closed_at=trade.get("closed_at"),
                status=trade.get("status", "open"),
                signal_id=trade.get("signal_id"),
                extra_data=trade.get("metadata", {})
            )
            session.add(t)
            session.commit()
            
            return t.id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error guardando trade: {e}")
            return 0
        finally:
            session.close()
    
    def get_open_trades(self) -> List[TradeHistory]:
        """Obtiene trades abiertos"""
        session = self.get_session()
        
        try:
            return session.query(TradeHistory).filter(
                TradeHistory.status == "open"
            ).all()
        finally:
            session.close()
    
    def get_trade_stats(self, days: int = 30) -> Dict[str, Any]:
        """Obtiene estadísticas de trading"""
        session = self.get_session()
        
        try:
            cutoff = datetime.now() - timedelta(days=days)
            trades = session.query(TradeHistory).filter(
                TradeHistory.opened_at >= cutoff,
                TradeHistory.status == "closed"
            ).all()
            
            if not trades:
                return {"total_trades": 0}
            
            total_profit = sum(t.profit or 0 for t in trades)
            wins = sum(1 for t in trades if (t.profit or 0) > 0)
            
            return {
                "total_trades": len(trades),
                "winning_trades": wins,
                "losing_trades": len(trades) - wins,
                "win_rate": wins / len(trades) if trades else 0,
                "total_profit": total_profit,
                "avg_profit": total_profit / len(trades) if trades else 0
            }
            
        finally:
            session.close()
    
    # ========== Logs ==========
    
    def log_agent(self, agent_name: str, action: str, result: str, 
                  success: bool, execution_time_ms: float = 0):
        """Registra una acción de agente"""
        session = self.get_session()
        
        try:
            log = AgentLog(
                agent_name=agent_name,
                action=action,
                result=result[:1000] if result else "",  # Limitar tamaño
                success=success,
                execution_time_ms=execution_time_ms
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error guardando log: {e}")
        finally:
            session.close()


# Singleton
_storage_instance: Optional[Storage] = None


def get_storage() -> Storage:
    """Obtiene instancia singleton del Storage"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = Storage()
    return _storage_instance


if __name__ == "__main__":
    # Test básico
    print("=" * 50)
    print("Test de Storage")
    print("=" * 50)
    
    storage = get_storage()
    
    # Test guardar señal
    signal_id = storage.save_signal({
        "symbol": "EURUSD",
        "type": "BUY",
        "strength": 0.75,
        "technical_score": 0.8,
        "sentiment_score": 0.6,
        "news_score": 0.7,
        "combined_score": 0.72
    })
    print(f"\nSeñal guardada con ID: {signal_id}")
    
    # Test obtener señales
    signals = storage.get_recent_signals()
    print(f"Señales recientes: {len(signals)}")
    
    # Test stats
    stats = storage.get_trade_stats()
    print(f"Estadísticas: {stats}")
