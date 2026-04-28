#include <asio.hpp>

#include <iostream>
#include <string>

#include "common/protocol.hpp"

using asio::ip::tcp;

static tcp::socket* g_sock = nullptr;
static asio::streambuf g_buf;

static void send_line(const std::string& s)
{
    asio::write(*g_sock, asio::buffer(s + "\n"));
}

static std::string recv_line()
{
    asio::read_until(*g_sock, g_buf, '\n');
    std::istream is(&g_buf);
    std::string line;
    std::getline(is, line);
    if (!line.empty() && line.back() == '\r') line.pop_back();
    return line;
}

static std::string recv_letter()
{
    std::string result;
    while (true)
    {
        std::string line = recv_line();
        if (line == ".") break;
        result += line + "\n";
    }
    return result;
}

static void print_help()
{
    std::cout <<
        "Help:\n"
        "  send <recipient1>[,2,3,blah,blah...]\n"
        "  read\n"
        "  quit\n"
        "  help\n";
}

int main(int argc, char* argv[])
{
    system("chcp 65001");
    if (argc < 2)
    {
        std::cerr << "Usage: mail <username> [<host>]\n";
        return 1;
    }
    std::string username = argv[1];
    std::string host = (argc >= 3) ? argv[2] : "127.0.0.1";

    try
    {
        asio::io_context io;
        tcp::resolver resolver(io);

        auto endpoints = resolver.resolve(host, std::to_string(proto::PORT));
        tcp::socket sock(io);
        asio::connect(sock, endpoints);
        g_sock = &sock;
        std::cout << "[mail] connected to " << host << ":" << proto::PORT << "\n";

        send_line("REGISTER " + username);
        std::string resp = recv_line();
        if (!resp.starts_with("OK"))
        {
            std::cerr << "Registration error: " << resp << "\n";
            return 1;
        }
        std::cout << "[mail] you're logged in as «" << username << "»\n";
        print_help();

        while (true)
        {
            std::cout << "> ";
            std::string cmd;
            if (!std::getline(std::cin, cmd)) break; // EOF
            if (cmd.empty()) continue;

            if (cmd.starts_with("send ") || cmd.starts_with("send\t"))
            {
                std::string to = cmd.substr(5);
                while (!to.empty() && (to.front() == ' ' || to.front() == '\t'))
                    to.erase(to.begin());
                if (to.empty())
                {
                    std::cout << "Recipient\n";
                    continue;
                }

                send_line("SEND " + to);
                resp = recv_line();
                if (!resp.starts_with("OK"))
                {
                    std::cout << "Server: " << resp << "\n";
                    continue;
                }

                std::cout << "Enter letter, end with newlined '.':\n";
                std::string body_line;
                while (std::getline(std::cin, body_line))
                {
                    send_line(body_line);
                    if (body_line == ".") break;
                }
                resp = recv_line();
                std::cout << "Server: " << resp << "\n";
            }
            else if (cmd == "read")
            {
                send_line("READ");
                resp = recv_line();
                if (resp == "LETTER")
                {
                    std::string letter = recv_letter();
                    std::cout << "─── New letter ───────────────────\n"
                        << letter
                        << "──────────────────────────────────\n";
                }
                else
                {
                    std::cout << "Server: " << resp << "\n";
                }
            }
            else if (cmd == "quit" || cmd == "exit")
            {
                send_line("QUIT");
                recv_line();
                break;
            }
            else if (cmd == "help")
            {
                print_help();
            }
            else
            {
                std::cout << "Unknown command, invoke 'help'.\n";
            }
        }

        sock.close();
        std::cout << "[mail] session terminated.\n";
    }
    catch (std::exception& e)
    {
        std::cerr << "mail error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
