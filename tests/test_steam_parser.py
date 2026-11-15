from decimal import Decimal

from bs4 import BeautifulSoup

from app.adapters.steam import SteamAdapter, _parse_brl


def test_parse_brl_thousands_and_decimal_separator():
    assert _parse_brl("R$ 1.299,00") == Decimal("1299.00")
    assert _parse_brl("R$16,74") == Decimal("16.74")


def test_parse_steam_search_result_row():
    html = '''
    <a class="search_result_row" data-ds-appid="227300"
       href="https://store.steampowered.com/app/227300/Euro_Truck_Simulator_2/">
      <div class="search_capsule"><img src="https://cdn.example/capsule.jpg"></div>
      <div class="responsive_search_name_combined">
        <div class="search_name"><span class="title">Euro Truck Simulator 2</span></div>
        <div class="search_platforms"><span class="platform_img win"></span><span class="platform_img.linux"></span></div>
        <div class="search_released">12/out./2012</div>
        <div class="search_reviewscore"><span class="search_review_summary" data-tooltip-html="Extremamente positivas"></span></div>
        <div class="search_price_discount_combined" data-price-final="1674">
          <div class="discount_block">
            <div class="discount_pct">-75%</div>
            <div class="discount_prices">
              <div class="discount_original_price">R$66,99</div>
              <div class="discount_final_price">R$16,74</div>
            </div>
          </div>
        </div>
      </div>
    </a>'''
    row = BeautifulSoup(html, "html.parser").select_one("a.search_result_row")
    result = SteamAdapter._parse_row(row)
    assert result is not None
    assert result["external_id"] == "227300"
    assert result["title"] == "Euro Truck Simulator 2"
    assert result["current_price"] == Decimal("16.74")
    assert result["original_price"] == Decimal("66.99")
    assert result["discount_percent"] == Decimal("75")
    assert result["currency"] == "BRL"
