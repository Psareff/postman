#pragma once
#include <string>
#include <vector>
#include <sstream>

// ─── Текстовый протокол ───────────────────────────────────────────────
// Каждое сообщение — одна строка (завершается \n), кроме тела письма.
//
// Клиент → Сервер:
//   REGISTER <name>\n              — зарегистрировать абонента
//   SEND <to1>[,to2,...]\n         — начало письма (далее строки тела, ".\n" — конец)
//   READ\n                         — прочитать первое письмо из своего ящика
//   QUIT\n                         — завершить сессию
//
// Сервер → Клиент:
//   OK\n                           — успех
//   ERR <reason>\n                 — ошибка
//   LETTER\n<строки тела>.\n       — доставка письма

namespace proto {

inline constexpr uint16_t PORT = 9000;

// Разбить CSV-список получателей
inline std::vector<std::string> split_recipients(const std::string& csv) {
    std::vector<std::string> res;
    std::istringstream ss(csv);
    std::string tok;
    while (std::getline(ss, tok, ','))
        if (!tok.empty()) res.push_back(tok);
    return res;
}

} // namespace proto
