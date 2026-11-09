"""Assistant IA local du studio (orchestration côté Python).

- ``llm_client`` : adaptateur vers une API compatible OpenAI (llama.cpp,
  LM Studio, vLLM, etc.) — aucun cloud, aucune clé réutilisée ;
- ``capabilities`` : manifeste de ce que le studio sait réellement faire ;
- ``retrieval`` : recherche lexicale bornée sur les connaissances locales ;
- ``context`` : assemblage du prompt pour petit modèle, budget respecté ;
- ``proposals`` : contrat des propositions et application des opérations ;
- ``tools`` : registre borné des outils autorisés ;
- ``service`` : boucle demande -> proposition -> validation -> réparation.
"""
