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
import json


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


class DailyMemory(Base):
    """Modelo para memoria diaria resumida"""
    __tablename__ = 'daily_memory'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(20), nullable=False, unique=True)  # YYYY-MM-DD
    summary = Column(Text, nullable=False)
    stats = Column(JSON)
    created_at = Column(DateTime, default=datetime.now)


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


class SnakeSession(Base):
    """Modelo para sesiones de control temporal (Snake Mode)"""
    __tablename__ = 'snake_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket = Column(Integer, nullable=False)  # ID de la orden en MT5
    symbol = Column(String(20), nullable=False)
    
    # Configuración de tiempo
    start_time = Column(DateTime, default=datetime.now)
    duration_seconds = Column(Integer, nullable=False)  # Duración pactada (e.g. 30, 60)
    end_time_planned = Column(DateTime, nullable=False)
    
    # Estado
    status = Column(String(20), default="ACTIVE")  # ACTIVE, COMPLETED, ABORTED
    outcome = Column(String(20))  # SUCCESS, FAIL, NEUTRAL
    
    # Datos iniciales para comparación
    entry_price = Column(Float)
    initial_profit = Column(Float)
    
    # Evaluación final
    final_profit = Column(Float)
    notes = Column(Text)  # Razón del cierre (Time expire, SL logic, etc)



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
                    extra_data=item.metadata
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
                    currency=item.metadata.get("currency", ""),
                    impact=item.metadata.get("impact", "low"),
                    event_time=item.metadata.get("time", ""),
                    actual=item.metadata.get("actual", ""),
                    forecast=item.metadata.get("forecast", ""),
                    previous=item.metadata.get("previous", ""),
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

    def import_mt5_history(self, deals: List[Dict[str, Any]]) -> int:
        """
        Importa y reconstruye el historial completo desde deals de MT5.
        Diferencia de sync_closed_trades porque crea el trade si no existe.
        """
        if not deals:
            return 0
            
        session = self.get_session()
        imported_count = 0
        
        try:
            # Agrupar deals por ticket de posición
            deals_by_ticket = {}
            for d in deals:
                ticket = d['ticket']
                if ticket not in deals_by_ticket:
                    deals_by_ticket[ticket] = []
                deals_by_ticket[ticket].append(d)
            
            for ticket, t_deals in deals_by_ticket.items():
                # Buscar si ya existe este trade en la DB
                trade = session.query(TradeHistory).filter(TradeHistory.ticket == ticket).first()
                
                # Encontrar deal de entrada (entry_type=0) y salida (entry_type=1)
                entry_deal = next((d for d in t_deals if d.get('entry_type') == 0), None)
                exit_deal = next((d for d in t_deals if d.get('entry_type') == 1), None)
                
                if not trade:
                    # Crear nuevo trade si tenemos al menos la ENTRADA (ideal) o la SALIDA (mínimo)
                    if entry_deal:
                        trade = TradeHistory(
                            ticket=ticket,
                            symbol=entry_deal['symbol'],
                            order_type=entry_deal['type'],
                            volume=entry_deal['volume'],
                            open_price=entry_deal['price'],
                            opened_at=entry_deal['timestamp'],
                            status="open"
                        )
                        session.add(trade)
                    elif exit_deal:
                        # Si no tenemos la entrada (fuera del rango de días),
                        # usamos los datos de la salida para reconstruir lo básico.
                        # El precio de entrada real no lo tenemos, usamos el de salida como base
                        # para que no falle el cálculo de profit.
                        trade = TradeHistory(
                            ticket=ticket,
                            symbol=exit_deal['symbol'],
                            order_type="SELL" if exit_deal['type'] == "BUY" else "BUY", # Invertir la salida
                            volume=exit_deal['volume'],
                            open_price=exit_deal['price'], # Desconocido, usamos salida para evitar saltos raros
                            opened_at=exit_deal['timestamp'] - timedelta(hours=1), # Estimación
                            status="open"
                        )
                        session.add(trade)
                
                # Actualizar datos de cierre si hay deal de salida
                if trade and exit_deal:
                    trade.status = "closed"
                    trade.close_price = exit_deal['price']
                    trade.profit = exit_deal['profit'] + exit_deal.get('commission', 0) + exit_deal.get('swap', 0)
                    trade.closed_at = exit_deal['timestamp']
                    
                    # Si acabamos de crear el trade desde la salida, ajustamos el precio de entrada
                    # para que el profit coincida con el reportado por MT5.
                    # profit = (p_close - p_open) * vol * mult (aprox) -> p_open = p_close - (profit / (vol * mult))
                    # Pero es más fácil confiar en el profit del deal de MT5 y dejar el open_price decorativo.
                
                imported_count += 1
            
            session.commit()
            if imported_count > 0:
                logger.info(f"Importados/Actualizados {imported_count} trades desde historial MT5")
                
        except Exception as e:
            session.rollback()
            logger.error(f"Error importando historial: {e}")
        finally:
            session.close()
            
        return imported_count
    
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
    


    # ========== Memoria Diaria ==========
    
    def save_daily_memory(self, date: str, summary: str, stats: Dict[str, Any]) -> bool:
        """Guarda un resumen de memoria diaria"""
        session = self.get_session()
        try:
            # Verificar si ya existe
            exists = session.query(DailyMemory).filter(DailyMemory.date == date).first()
            if exists:
                exists.summary = summary
                exists.stats = stats
                exists.created_at = datetime.now()
            else:
                mem = DailyMemory(
                    date=date,
                    summary=summary,
                    stats=stats
                )
                session.add(mem)
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error guardando memoria diaria: {e}")
            return False
    def get_trade_history(self, status: Optional[str] = None, limit: int = 100) -> List[TradeHistory]:
        """Obtiene el historial de trades filtrado por status"""
        session = self.get_session()
        try:
            query = session.query(TradeHistory)
            if status:
                query = query.filter(TradeHistory.status == status)
            return query.order_by(TradeHistory.opened_at.desc()).limit(limit).all()
        finally:
            session.close()

    def get_all_trade_results(self) -> List[Any]:
        """
        Obtiene todos los trades convertidos a objetos TradeResult (para analítica).
        """
        from strategies.analytics import TradeResult
        
        session = self.get_session()
        try:
            trades = session.query(TradeHistory).filter(TradeHistory.status == "closed").all()
            results = []
            for t in trades:
                # Calcular duración
                duration = 0
                if t.closed_at and t.opened_at:
                    duration = int((t.closed_at - t.opened_at).total_seconds() // 60)
                
                # Calcular pips (estimación simple si no hay datos específicos de pips en DB)
                pips = 0.0
                if t.open_price and t.close_price:
                    # Esto es una simplificación, dependería del símbolo (5 vs 3 decimales)
                    pips = abs(t.close_price - t.open_price) * 10000
                
                # Calcular R-Multiple
                r_mult = 0.0
                if t.sl and t.sl > 0 and t.open_price:
                    risk_per_share = abs(t.open_price - t.sl)
                    if risk_per_share > 0:
                        diff_price = t.close_price - t.open_price
                        if str(t.order_type).upper() in ["SELL", "1"]:
                            diff_price = -diff_price
                        
                        r_mult = diff_price / risk_per_share

                results.append(TradeResult(
                    ticket=t.ticket,
                    symbol=t.symbol,
                    order_type=t.order_type,
                    volume=t.volume,
                    open_price=t.open_price,
                    close_price=t.close_price,
                    open_time=t.opened_at,
                    close_time=t.closed_at,
                    profit=t.profit or 0.0,
                    pips=pips,
                    duration_minutes=duration,
                    r_multiple=r_mult
                ))
            return results
        except Exception as e:
            logger.error(f"Error cargando TradeResults: {e}")
            return []
        finally:
            session.close()

    def get_latest_memory(self) -> Optional[DailyMemory]:

        """Obtiene el último resumen de memoria disponible"""
        session = self.get_session()
        try:
            return session.query(DailyMemory).order_by(DailyMemory.date.desc()).first()
        finally:
            session.close()

    def get_memory_by_date(self, date: str) -> Optional[DailyMemory]:
        """Obtiene la memoria de una fecha específica"""
        session = self.get_session()
        try:
            return session.query(DailyMemory).filter(DailyMemory.date == date).first()
        finally:
            session.close()

    # ========== Logs de Agentes ==========

    def save_agent_log(self, agent_name: str, action: str, result: str, success: bool, execution_time: float = 0):

        """Guarda un log detallado de la acción de un agente"""
        session = self.get_session()
        try:
            log = AgentLog(
                agent_name=agent_name,
                action=action,
                result=str(result),  # Asegurar que sea string
                success=success,
                execution_time_ms=float(execution_time),
                created_at=datetime.now()
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error guardando agent log: {e}")
        finally:
            session.close()

    def fetch_system_logs(self, limit: int = 50) -> List[AgentLog]:
        """Obtiene los logs más recientes de los agentes para la consola"""
        session = self.get_session()
        try:
            return session.query(AgentLog).order_by(AgentLog.created_at.desc()).limit(limit).all()
        finally:
            session.close()

    def clear_trade_history(self):
        """Borra todo el historial de trades"""
        session = self.get_session()
        try:
            session.query(TradeHistory).delete()
            session.commit()
            logger.info("Historial de trades borrado")
        except Exception as e:
            session.rollback()
            logger.error(f"Error borrando historial: {e}")
        finally:
            session.close()

    def clear_agent_logs(self):
        """Borra todos los logs de agentes"""
        session = self.get_session()
        try:
            session.query(AgentLog).delete()
            session.commit()
            logger.info("Logs de agentes borrados")
        except Exception as e:
            session.rollback()
            logger.error(f"Error borrando logs: {e}")
        finally:
            session.close()

    # ========== Snake Sessions (Timing Control) ==========

    def create_snake_session(self, ticket: int, symbol: str, duration_seconds: int, entry_price: float, current_profit: float) -> int:
        """Crea una nueva sesión de control temporal para una orden existente"""
        session = self.get_session()
        try:
            # Desactivar sesiones anteriores para este ticket si las hay
            old_sessions = session.query(SnakeSession).filter(
                SnakeSession.ticket == ticket,
                SnakeSession.status == "ACTIVE"
            ).all()
            for old in old_sessions:
                old.status = "ABORTED"
                old.notes = "Replaced by new session"
            
            now = datetime.now()
            planned_end = now + timedelta(seconds=duration_seconds)
            
            new_session = SnakeSession(
                ticket=ticket,
                symbol=symbol,
                duration_seconds=duration_seconds,
                start_time=now,
                end_time_planned=planned_end,
                entry_price=entry_price,
                initial_profit=current_profit,
                status="ACTIVE"
            )
            
            session.add(new_session)
            session.commit()
            logger.info(f"🐍 Snake Session creada para Ticket #{ticket} ({duration_seconds}s)")
            return new_session.id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error creando Snake Session: {e}")
            return 0
        finally:
            session.close()

    def get_active_snake_sessions(self) -> List[SnakeSession]:
        """Obtiene todas las sesiones Snake activas"""
        session = self.get_session()
        try:
            return session.query(SnakeSession).filter(
                SnakeSession.status == "ACTIVE"
            ).all()
        finally:
            session.close()

    def update_snake_session(self, session_id: int, status: str, outcome: str = None, final_profit: float = None, notes: str = None):
        """Actualiza el estado de una sesión Snake"""
        session = self.get_session()
        try:
            s = session.query(SnakeSession).filter(SnakeSession.id == session_id).first()
            if s:
                s.status = status
                if outcome: s.outcome = outcome
                if final_profit is not None: s.final_profit = final_profit
                if notes: s.notes = notes
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error actualizando Snake Session: {e}")
        finally:
            session.close()



# Singleton


_storage_instance: Optional[Storage] = None


def get_storage() -> Storage:
    """Obtiene instancia singleton del Storage"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = Storage()
    
    # Verificación de seguridad para evitar AttributeErrors por cache
    if not hasattr(_storage_instance, 'get_all_trade_results'):
        logger.warning("Singleton de Storage desactualizado. Forzando re-instanciación.")
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
