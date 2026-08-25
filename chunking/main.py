# chunking/main.py
import logging
from pathlib import Path

from chunking.chunk_orchestrator import ChunkOrchestrator
from scraping.content_cleaner import ContentCleaner
from scraping.models import ScrapingStats
from utils.cleaner_utils import CleanerConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

PROJECT_DIR = "outputs/raw_markdown"

config = CleanerConfig(
    min_line_length=30,
    output_dir_name="clean_markdown",
    input_dir_name="raw_markdown"
)

cleaner = ContentCleaner(PROJECT_DIR, config)

print("=" * 80)
print("🧹 NETTOYAGE DE MARKDOWN POUR RAG")
print("=" * 80)
print(f"📁 Entrée: {cleaner.input_dir}")
print(f"📁 Sortie: {cleaner.output_dir}")
print("")

files_to_clean = [
    str(f) for f in Path(PROJECT_DIR).glob("*.md")
]
existing_files = [f for f in files_to_clean if Path(f).exists()][:3]

if existing_files:
    print(f"📋 Nettoyage de {len(existing_files)} fichiers spécifiques")

    contents = []
    urls_scraped = []
    file_paths = []
    for f in existing_files:
        file_paths.append(str(f))
        urls_scraped.append("")
        try:
            contents.append(Path(f).read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            contents.append("")

    stats = ScrapingStats(
        total=len(existing_files),
        files=file_paths,
        urls_scraped=urls_scraped,
        contents=contents,
    )
    results = cleaner.process_all(stats)

    project_dir = r"C:\Users\ghofr\Downloads\mes_fichier\data_testing"

    orchestrator = ChunkOrchestrator()
    chunk_results = orchestrator.process_documents(
        cleaning_results=results,
        project_dir=project_dir,
        save_output=True,
        generate_report=True
    )

    print("\n" + "=" * 80)
    print("📋 APERÇU DES CHUNKS")
    print("=" * 80)

    all_chunks = chunk_results.get("all_chunks", [])
    for i, chunk in enumerate(all_chunks[:5]):
        print(f"\n🔹 CHUNK {i + 1}: {chunk.metadata.chunk_id}")
        print(f"   Document: {chunk.metadata.doc_title}")
        print(f"   Section: {' > '.join(chunk.metadata.heading_path)}")
        print(f"   Question: {chunk.metadata.question}")
        print(f"   Angle: {chunk.metadata.angle}")
        print(f"   Type: {chunk.metadata.chunk_type.value}")
        print(f"   Tokens: {chunk.metadata.token_count}")
        print(f"   Contenu: {chunk.content[:200]}...")

    rag_chunks = orchestrator.get_chunks_for_rag(chunks=all_chunks)
    print(f"\n📊 {len(rag_chunks)} chunks prêts pour RAG")
else:
    print("⚠️ Aucun fichier trouvé")