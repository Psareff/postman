#include <asio.hpp>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_set>
#include <vector>

#include "common/protocol.hpp"

namespace fs = std::filesystem;
using asio::ip::tcp;

static const fs::path MAILBOX_DIR = "mailboxes";

static std::mutex g_mutex;
static std::unordered_set<std::string> g_users;

static fs::path mailbox_path(const std::string& name)
{
    return MAILBOX_DIR / (name + ".mbox");
}

static void append_letter(const std::string& to, const std::string& letter)
{
    std::lock_guard lk(g_mutex);
    std::ofstream f(mailbox_path(to), std::ios::app);
    f << letter << "===\n";
}

static std::string pop_letter(const std::string& name)
{
    std::lock_guard lk(g_mutex);
    auto path = mailbox_path(name);
    if (!fs::exists(path)) return {};

    std::ifstream in(path);
    std::string content((std::istreambuf_iterator<char>(in)),
                        std::istreambuf_iterator<char>());
    in.close();
    if (content.empty()) return {};

    auto pos = content.find("===\n");
    if (pos == std::string::npos) return {};

    std::string letter = content.substr(0, pos);
    std::string rest = content.substr(pos + 4);

    std::ofstream out(path, std::ios::trunc);
    out << rest;
    return letter;
}

class Session : public std::enable_shared_from_this<Session>
{
public:
    explicit Session(tcp::socket sock) : sock_(std::move(sock))
    {
    }

    void start() { read_line(); }

private:
    tcp::socket sock_;
    asio::streambuf buf_;
    std::string username_;
    bool in_send_{false};
    std::string letter_body_;
    std::vector<std::string> recipients_;

    void send(std::string msg)
    {
        auto self = shared_from_this();
        asio::async_write(sock_, asio::buffer(msg),
                          [self](std::error_code, std::size_t)
                          {
                          });
    }

    void read_line()
    {
        auto self = shared_from_this();
        asio::async_read_until(sock_, buf_, '\n',
                               [self](std::error_code ec, std::size_t)
                               {
                                   if (ec) return;
                                   std::istream is(&self->buf_);
                                   std::string line;
                                   std::getline(is, line);
                                   if (!line.empty() && line.back() == '\r') line.pop_back();
                                   self->handle_line(line);
                               });
    }

    void handle_line(const std::string& line)
    {
        if (in_send_)
        {
            if (line == ".")
            {
                in_send_ = false;
                deliver();
            }
            else
            {
                letter_body_ += line + "\n";
            }
            read_line();
            return;
        }

        if (line.starts_with("REGISTER "))
        {
            handle_register(line.substr(9));
        }
        else if (line.starts_with("SEND "))
        {
            handle_send(line.substr(5));
        }
        else if (line == "READ")
        {
            handle_read();
        }
        else if (line == "QUIT")
        {
            send("OK bye\n");
            return;
        }
        else
        {
            send("ERR unknown command\n");
        }
        read_line();
    }

    void handle_register(const std::string& name)
    {
        std::lock_guard lk(g_mutex);
        if (g_users.count(name))
        {
            // Do nothing
            // Just kidding. Let this user enter as he already has mailbox
            std::cout << "[postman] logged in: " << name << "\n";
        }
        else
        {
            g_users.insert(name);
            fs::create_directories(MAILBOX_DIR);
            if (!fs::exists(mailbox_path(name)))
            {
                std::ofstream(mailbox_path(name));
            }
            std::cout << "[postman] registered: " << name << "\n";
        }
        username_ = name;
        send("OK registered\n");
    }

    void handle_send(const std::string& csv)
    {
        if (username_.empty())
        {
            send("ERR not registered\n");
            return;
        }
        recipients_ = proto::split_recipients(csv);
        {
            std::lock_guard lk(g_mutex);
            for (auto& r : recipients_)
                if (!g_users.count(r))
                {
                    send("ERR unknown recipient: " + r + "\n");
                    recipients_.clear();
                    return;
                }
        }
        letter_body_.clear();
        in_send_ = true;
        send("OK send body, end with .\n");
    }

    void deliver()
    {
        std::string letter = "From: " + username_ + "\n" + letter_body_;
        for (auto& r : recipients_)
            append_letter(r, letter);
        std::cout << "[postman] letter from " << username_
            << " to " << recipients_.size() << " recipient(s)\n";
        send("OK delivered\n");
    }

    void handle_read()
    {
        if (username_.empty())
        {
            send("ERR not registered\n");
            return;
        }
        auto letter = pop_letter(username_);
        if (letter.empty())
        {
            send("ERR mailbox empty\n");
        }
        else
        {
            send("LETTER\n" + letter + ".\n");
            std::cout << "[postman] delivered mail to " << username_ << "\n";
        }
    }
};

class Server
{
public:
    Server(asio::io_context& io, uint16_t port)
        : acceptor_(io, tcp::endpoint(tcp::v4(), port))
    {
        std::cout << "[postman] listening on port " << port << "\n";
        accept();
    }

private:
    tcp::acceptor acceptor_;

    void accept()
    {
        acceptor_.async_accept(
            [this](std::error_code ec, tcp::socket sock)
            {
                if (!ec)
                {
                    std::cout << "[postman] client connected: "
                        << sock.remote_endpoint() << "\n";
                    std::make_shared<Session>(std::move(sock))->start();
                }
                accept();
            });
    }
};

int main()
{
    system("chcp 65001");
    try
    {
        asio::io_context io;
        Server server(io, proto::PORT);
        io.run();
    }
    catch (std::exception& e)
    {
        std::cerr << "postman error: " << e.what() << "\n";
        return 1;
    }
}
