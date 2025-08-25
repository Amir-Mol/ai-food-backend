"""
Generates dense vector embeddings for all recipes in a dataset.

This code loads processed recipe data from a parquet file, creates descriptive 
text documents for each recipe (combining title, description, tags, and ingredients), 
and uses the SentenceTransformer 'all-MiniLM-L6-v2' model to convert them into 
vector embeddings. The resulting embeddings are saved to a NumPy file for fast 
loading in recommendation tasks.
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import PROCESSED_RECIPE_FILE, RECIPE_EMBEDDINGS_FILE

def create_recipe_document(recipe: pd.Series) -> str:
    """
    Creates a single text string from a recipe's key fields to be used for embedding.
    """
    # Join the list-based columns into clean, comma-separated strings
    ingredients_str = ', '.join(recipe.get('ingredients_title', []))
    tags_str = ', '.join(recipe.get('tags', []))

    # Combine the fields into a single, descriptive document
    document = (
        f"Title: {recipe.get('title', '')}. "
        f"Ingredients: {ingredients_str}. "
        f"Tags: {tags_str}."
    )
    return document

def generate_recipe_embeddings(data_path, output_path):
    """
    Generates and saves embeddings for all recipes from the processed data file.
    """
    print("Loading processed data...")
    df = pd.read_parquet(data_path)

    print("Loading embedding model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    print("Creating recipe documents for embedding...")
    df['embedding_document'] = df.apply(create_recipe_document, axis=1)

    print("Generating embeddings... (This may take a few minutes)")
    embeddings = model.encode(df['embedding_document'].tolist(), show_progress_bar=True)

    print(f"Generated {len(embeddings)} embeddings.")
    np.save(output_path, embeddings)
    print(f"Embeddings successfully saved to {output_path}")

if __name__ == '__main__':
    generate_recipe_embeddings(PROCESSED_RECIPE_FILE, RECIPE_EMBEDDINGS_FILE)

