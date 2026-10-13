---
name: unslop
type: skill
description: Elimina marcas e vicios de escrita de IA de relatorios tecnicos, documentacao, sumarios executivos, PRs e notas.
disable-model-invocation: true
---

# Unslop

Edit text to remove AI patterns and boilerplate. Scan for the patterns below, then rewrite. Preserve technical meaning and maintain a concise, professional tone in both Portuguese and English.

## Regras de Deteccao e Correcao (Stable IDs)

Os numeros das regras sao identificadores estaveis. Nunca renumere para manter compatibilidade com outras skills e referencias.

### Conteudo (Content)

3. **Superficial -ing phrases.** "highlighting...", "ensuring...", "reflecting...", "showcasing...", "fostering...". Em portugues: "visando a...", "evidenciando...", "garantindo que...", "demonstrando...". Exclua ou substitua pelo mecanismo tecnico real e fonte concreta.
5. **Vague attributions.** "Experts believe", "Industry reports suggest", "Some critics argue". Em portugues: "Especialistas apontam", "Estudos sugerem", "Boas praticas recomendam". Cite a norma ou fonte exata (ex.: NIST SP 800-115 §4, OWASP ASVS v4.0) ou delete a atribuicao.

### Linguagem (Language)

7. **AI vocabulary.** Additionally, crucial, delve, enduring, enhance, fostering, garner, interplay, intricate, landscape (abstrato), pivotal, showcase, tapestry (abstrato), testament, underscore, vibrant.
   Em portugues: "crucial", "fundamental", "vital", "robusto", "aprimorar", "cenario/paisagem" (metaforico), "divisor de aguas", "notavel", "salientar", "ecossistema" (quando nao se refere a ecologia biologica), "holistico", "resiliencia" (como adjetivo vago), "postura solida". Substitua por palavras diretas ou dados concretos.
8. **Fancy ways to say "is".** "serves as", "stands as", "boasts", "features". Em portugues: "atua como", "figura como", "apresenta-se como", "ostenta". Use simplesmente "e" ou "tem".
9. **"Not just X, but Y."** Em portugues: "Nao apenas X, mas tambem Y". Va direto ao ponto sem construcao contrastiva artificial.
10. **Rule of three.** Nao force ideias em triades artificiais. Use o numero natural de itens.
11. **Synonym cycling.** Alternar sinonimos na mesma secao para evitar repetir a palavra (ex: protagonista, figura central, personagem principal). Escolha o termo tecnico exato e repita-o.
12. **False ranges.** "from X to Y" / "de X a Y" quando X e Y nao pertencem a uma escala continua mensuravel. Liste os topicos diretamente.

### Estilo e Formatacao (Style)

13. **Em dash overuse.** Proibido o uso de travessoes duplos (`—`). Use pontos finais ou virgulas. Se a oracao precisa de separacao, termine a frase ou use virgula.
14. **Colon overuse.** Dois-pontos servem para introduzir listas ou blocos de codigo, nunca como muleta conectiva no meio de frases. Reescreva para que a declaracao se sustente sozinha.
15. **Boldface overuse.** Nao coloque em negrito cada sigla, substantivo proprio ou termo tecnico. Reserve negrito para dados-chave ou nomes de tabelas/campos.
16. **Inline-header lists.** Banida a construcao de bullet com rotulo em negrito seguido de dois-pontos que apenas repete a frase: "**Desempenho:** O desempenho melhorou...". Converta em texto corrido ou use lead-in em negrito seguido de ponto final e conteudo factual novo.
17. **Title case headings.** Use Sentence case em titulos e subtitulos (apenas a primeira letra e substantivos proprios em maiuscula).
18. **Decorative emojis.** Remova emojis decorativos de cabeçalhos, marcadores e titulos (`📌`, `💡`, `🚀`, `🛡️`, `✅`, etc.).
19. **Curly quotes.** Use sempre aspas retas (`"` e `'`).

### Artefatos de Comunicacao de Chatbot

20. **Chatbot phrases.** Remova introducoes e despedidas de assistente: "Espero ter ajudado!", "Fique a vontade para perguntar", "Certamente!", "Com certeza!", "Com certeza, posso ajudar com isso!".
22. **Sycophantic tone.** Remova bajulacao e validacao excessiva: "Otima pergunta!", "Voce esta absolutamente certo!". Responda diretamente ao ponto tecnico.

### Enchimento (Filler)

23. **Filler phrases.** "In order to" -> "To". "Due to the fact that" -> "Because". Em portugues: "A fim de" / "Com o objetivo de" -> "Para". "Devido ao fato de que" -> "Porque". Delete sumariamente: "E importante ressaltar que", "Vale destacar que", "Cumpre salientar", "No que diz respeito a".
24. **Excessive hedging.** "poderia potencialmente vir a indicar que talvez" -> "pode indicar" ou o fato comprovado.
25. **Generic conclusions.** "O futuro parece promissor", "A infraestrutura demonstra alinhamento continuo com os mais altos padroes". Apresente os proximos passos tecnicos, prazos e responsaveis. Se nao houver nada concreto a acrescentar, encerre o documento sem conclusao vazia.

### Jargao e Metaforas Abstratas

26. **Abstract metaphor nouns.** Substrato, vetor (quando usado como modo/metodo e nao matematica/fisica), nexo, locus, vantage, primitiva (como substantivo solto), superficie de API (use apenas API ou interfaces), norte magnetico, flywheel, alavanca. Use a palavra concreta (metodo, base, interface, meta).

### Linguagem Direta e Concreta (Plain Speech)

27. **Say what it does, not how it feels.** Nao descreva sensacoes como "banco de dados robusto", "codigo legivel", "postura solida". Diga o mecanismo ou o numero: "tempo de resposta p99 de 14ms", "0 vulnerabilidades ativas", "o validador bloqueia o build se a coluna for renomeada". Teste de ouro: se a frase puder ser copiada intacta para o relatorio de outra empresa, ela nao diz nada sobre esta. Corte-a.
28. **Shorten or split dense sentences.** Uma ideia central por frase. Se o leitor precisar reler para entender a sintaxe, divida em duas frases curtas.
29. **Active voice.** Prefira voz ativa. Identifique o agente: "os pacotes sao descartados pelo firewall" -> "o firewall descarta os pacotes".
30. **Cut adverbs, or use a stronger verb.** "executa muito rapidamente" -> informe o benchmark numérico em ms. "melhora significativamente" -> "reduz a latencia em 35%".
31. **Prefer the plain word.** "utilizar" -> "usar"; "facilitar" -> "ajudar"; "no ambito de" -> corte; "em virtude de" -> "por".
32. **Mannered prose.** Corte aforismos, personificacao de codigo ("o plano sabe o que fazer") e metaforas retoricas. Escreva o sentido literal.
33. **Over-compression.** Nao elimine artigos ou conectivos gramaticais a ponto de criar frases truncadas ou telegraficas inintutiveis. Escreva oracoes completas com sujeito, verbo e predicado.
