/*
 * AMOSTRAS FRA 2.0 - Telas do display (TTGO T-Display, ST7735 80x160)
 * ===================================================================
 * Interface local do instrumento: estado, configuracao recebida do
 * AmostrasFRA, andamento da varredura (com grafico |Z| ao vivo) e
 * resumo final.  Paisagem 160x80 (setRotation(1)).
 *
 * Honestidade de medicao: o AD5933 mede IMPEDANCIA (|Z| e fase).
 * A tensao exibida e' a de EXCITACAO CONFIGURADA (Vpp) e a corrente
 * e' ESTIMADA (Ipp ~= Vpp/|Z|) - rotuladas como "cfg"/"est" na tela.
 */
#ifndef TELAS_H
#define TELAS_H

#include <Arduino.h>

namespace telas {

// Inicializa TFT + backlight (PWM) e mostra a tela de abertura.
void inicia();

// Tela de estado (ocioso): chip detectado ou nao, temperatura e dica.
void estado(bool chipOk, double tempC);

// Tela de configuracao (apos comando "C" do AmostrasFRA).
void configuracao(double f0, double f1, uint16_t n,
                  int vppMv, int pga, uint16_t settle);

// Prepara a tela de varredura (zera historico e barra de progresso).
void iniciaVarredura(uint16_t nPontos, int vppMv);

// Atualiza um ponto da varredura: indice, frequencia, |Z| (ohm) e
// fase (graus). Desenha numeros, sparkline de |Z| e progresso.
void ponto(uint16_t i, uint16_t n, double f,
           double zmod, double faseGraus);

// Tela de resumo ao fim da varredura.
void fimVarredura(uint16_t n, double zMin, double zMax);

// Tela do modo calibracao (gain factor e fase do sistema).
void calibracao(double gainFactor, double faseSistema);

// Tela do modo excitacao continua (comando "V"): o VOUT fica ligado
// numa frequencia fixa para conferir os terminais do DUT no osciloscopio.
void excitacao(double f, int vppMv);

// Mensagem de erro em destaque.
void erro(const char *mensagem);

// Alterna o brilho do backlight (100% -> 50% -> 20% -> 100%).
void alternaBrilho();

}  // namespace telas

#endif  // TELAS_H
