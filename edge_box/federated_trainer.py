"""Project Claw 联邦学习训练器 - edge_box/federated_trainer.py"""
import asyncio, json, logging, sqlite3, hashlib, pickle, gzip
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

@dataclass
class DialoguePair:
    dialogue_id: str
    client_instruction: str
    merchant_response: str
    satisfaction_score: float
    timestamp: float

@dataclass
class TrainingConfig:
    model_name: str = "deepseek-ai/deepseek-7b"
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    learning_rate: float = 1e-4
    num_epochs: int = 3
    batch_size: int = 4
    max_seq_length: int = 512
    satisfaction_threshold: float = 0.8
    min_dialogue_pairs: int = 10

@dataclass
class AdapterMetadata:
    adapter_id: str
    model_name: str
    training_date: str
    num_samples: int
    avg_satisfaction: float
    device_id: str
    lora_config: Dict[str, Any]
    checksum: str = ""

class DialogueDataExtractor:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def extract_high_quality_dialogues(self, satisfaction_threshold: float = 0.8, limit: Optional[int] = None) -> List[DialoguePair]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            query = "SELECT session_id, client_message, merchant_message, satisfaction_score, timestamp FROM dialogues WHERE satisfaction_score >= ? AND client_message IS NOT NULL AND merchant_message IS NOT NULL ORDER BY timestamp DESC"
            params = [satisfaction_threshold]
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            dialogues = [DialoguePair(row[0], row[1], row[2], row[3], row[4]) for row in rows]
            logger.info(f"提取 {len(dialogues)} 个高质量对话对")
            return dialogues
        except Exception as e:
            logger.error(f"提取对话数据失败: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM dialogues")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM dialogues WHERE satisfaction_score >= 0.8")
            high_quality = cursor.fetchone()[0]
            cursor.execute("SELECT AVG(satisfaction_score) FROM dialogues")
            avg_satisfaction = cursor.fetchone()[0] or 0
            conn.close()
            return {"total_dialogues": total, "high_quality_dialogues": high_quality, "avg_satisfaction": avg_satisfaction}
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}

class LoRAFinetuner:
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.adapter_path = None
    
    async def load_model(self):
        try:
            logger.info(f"加载模型: {self.config.model_name}")
            try:
                from unsloth import FastLanguageModel
                self.model, self.tokenizer = FastLanguageModel.from_pretrained(
                    model_name=self.config.model_name,
                    max_seq_length=self.config.max_seq_length,
                    dtype=None,
                    load_in_4bit=True,
                )
                self.model = FastLanguageModel.get_peft_model(
                    self.model,
                    r=self.config.lora_r,
                    lora_alpha=self.config.lora_alpha,
                    lora_dropout=self.config.lora_dropout,
                    bias="none",
                    use_gradient_checkpointing="unsloth",
                    random_state=42,
                )
                logger.info("✓ 模型加载成功（使用 unsloth）")
            except ImportError:
                from peft import get_peft_model, LoraConfig, TaskType
                from transformers import AutoModelForCausalLM, AutoTokenizer
                self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
                base_model = AutoModelForCausalLM.from_pretrained(self.config.model_name, load_in_4bit=True, device_map="auto")
                lora_config = LoraConfig(r=self.config.lora_r, lora_alpha=self.config.lora_alpha, lora_dropout=self.config.lora_dropout, bias="none", task_type=TaskType.CAUSAL_LM)
                self.model = get_peft_model(base_model, lora_config)
                logger.info("✓ 模型加载成功（使用 peft）")
            return True
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            return False
    
    async def finetune(self, dialogues: List[DialoguePair]) -> Tuple[bool, Optional[str]]:
        try:
            if len(dialogues) < self.config.min_dialogue_pairs:
                logger.warning(f"样本数量不足: {len(dialogues)} < {self.config.min_dialogue_pairs}")
                return False, None
            
            success = await self.load_model()
            if not success:
                return False, None
            
            from datasets import Dataset
            from transformers import Trainer, TrainingArguments
            
            dataset = Dataset.from_dict({
                "instruction": [d.client_instruction for d in dialogues],
                "response": [d.merchant_response for d in dialogues],
            })
            
            def tokenize_function(examples):
                texts = [f"Instruction: {inst}\nResponse: {resp}" for inst, resp in zip(examples["instruction"], examples["response"])]
                return self.tokenizer(texts, truncation=True, max_length=self.config.max_seq_length, padding="max_length")
            
            tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["instruction", "response"])
            
            training_args = TrainingArguments(
                output_dir="./lora_adapter",
                num_train_epochs=self.config.num_epochs,
                per_device_train_batch_size=self.config.batch_size,
                learning_rate=self.config.learning_rate,
                logging_steps=10,
                save_strategy="epoch",
                fp16=True,
            )
            
            trainer = Trainer(model=self.model, args=training_args, train_dataset=tokenized_dataset)
            trainer.train()
            
            adapter_path = f"./lora_adapter_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.model.save_pretrained(adapter_path)
            self.adapter_path = adapter_path
            
            logger.info(f"✓ 微调完成，适配器已保存: {adapter_path}")
            return True, adapter_path
        except Exception as e:
            logger.error(f"微调失败: {e}")
            return False, None

class AdapterPackager:
    @staticmethod
    def package_adapter(adapter_path: str, metadata: AdapterMetadata) -> Tuple[bool, Optional[bytes]]:
        try:
            logger.info(f"打包适配器: {adapter_path}")
            adapter_files = {}
            adapter_dir = Path(adapter_path)
            for file_path in adapter_dir.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(adapter_dir)
                    with open(file_path, "rb") as f:
                        adapter_files[str(relative_path)] = f.read()
            
            package_data = {"metadata": asdict(metadata), "adapter_files": adapter_files, "timestamp": datetime.now().isoformat()}
            serialized = pickle.dumps(package_data)
            compressed = gzip.compress(serialized)
            logger.info(f"✓ 适配器打包完成，大小: {len(compressed) / 1024 / 1024:.2f} MB")
            return True, compressed
        except Exception as e:
            logger.error(f"打包适配器失败: {e}")
            return False, None
    
    @staticmethod
    def calculate_checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

class AdapterUploader:
    def __init__(self, hub_url: str, device_id: str):
        self.hub_url = hub_url
        self.device_id = device_id
        self.client = httpx.AsyncClient(timeout=300.0)
    
    async def upload_adapter(self, adapter_data: bytes, metadata: AdapterMetadata) -> Tuple[bool, str]:
        try:
            logger.info(f"上传适配器到 {self.hub_url}")
            checksum = AdapterPackager.calculate_checksum(adapter_data)
            metadata.checksum = checksum
            
            files = {
                "adapter": ("adapter.pkl.gz", adapter_data, "application/octet-stream"),
                "metadata": ("metadata.json", json.dumps(asdict(metadata)).encode(), "application/json")
            }
            data = {"device_id": self.device_id, "adapter_id": metadata.adapter_id, "checksum": checksum}
            
            response = await self.client.post(f"{self.hub_url}/upload", files=files, data=data)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✓ 适配器上传成功: {result}")
                return True, "适配器上传成功"
            else:
                logger.error(f"上传失败: {response.status_code} {response.text}")
                return False, f"上传失败: {response.status_code}"
        except Exception as e:
            logger.error(f"上传适配器失败: {e}")
            return False, f"错误: {str(e)}"

class FederatedTrainer:
    def __init__(self, db_path: str, hub_url: str, device_id: str, config: TrainingConfig = None):
        self.db_path = db_path
        self.hub_url = hub_url
        self.device_id = device_id
        self.config = config or TrainingConfig()
        self.data_extractor = DialogueDataExtractor(db_path)
        self.finetuner = LoRAFinetuner(self.config)
        self.uploader = AdapterUploader(hub_url, device_id)
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
    
    async def start(self):
        logger.info("启动联邦学习训练守护进程...")
        self.scheduler.add_job(self.train_and_upload, "cron", hour=3, minute=0, id="federated_training")
        self.scheduler.start()
        self.is_running = True
        logger.info("✓ 守护进程已启动，每天凌晨 3 点执行训练")
    
    async def stop(self):
        logger.info("停止联邦学习训练守护进程...")
        self.scheduler.shutdown()
        self.is_running = False
        logger.info("✓ 守护进程已停止")
    
    async def train_and_upload(self):
        logger.info("=" * 60)
        logger.info("开始联邦学习训练流程")
        logger.info("=" * 60)
        
        try:
            logger.info("\n第 1 步：获取数据库统计...")
            stats = self.data_extractor.get_statistics()
            logger.info(f"统计信息: {stats}")
            
            logger.info("\n第 2 步：提取高质量对话...")
            dialogues = self.data_extractor.extract_high_quality_dialogues(satisfaction_threshold=self.config.satisfaction_threshold)
            
            if len(dialogues) < self.config.min_dialogue_pairs:
                logger.warning(f"对话数量不足，跳过本次训练: {len(dialogues)} < {self.config.min_dialogue_pairs}")
                return
            
            logger.info("\n第 3 步：执行 LoRA 微调...")
            success, adapter_path = await self.finetuner.finetune(dialogues)
            
            if not success:
                logger.error("微调失败")
                return
            
            logger.info("\n第 4 步：打包适配器...")
            metadata = AdapterMetadata(
                adapter_id=f"adapter_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                model_name=self.config.model_name,
                training_date=datetime.now().isoformat(),
                num_samples=len(dialogues),
                avg_satisfaction=sum(d.satisfaction_score for d in dialogues) / len(dialogues),
                device_id=self.device_id,
                lora_config={"r": self.config.lora_r, "alpha": self.config.lora_alpha, "dropout": self.config.lora_dropout}
            )
            
            success, adapter_data = AdapterPackager.package_adapter(adapter_path, metadata)
            
            if not success:
                logger.error("打包适配器失败")
                return
            
            logger.info("\n第 5 步：上传适配器到联邦中心...")
            success, message = await self.uploader.upload_adapter(adapter_data, metadata)
            
            if success:
                logger.info(f"✓ 联邦学习训练流程完成: {message}")
            else:
                logger.error(f"✗ 上传失败: {message}")
        
        except Exception as e:
            logger.error(f"训练流程异常: {e}")
        
        finally:
            logger.info("=" * 60)
            logger.info("联邦学习训练流程结束")
            logger.info("=" * 60)
    
    async def manual_train(self):
        logger.info("手动触发联邦学习训练...")
        await self.train_and_upload()
